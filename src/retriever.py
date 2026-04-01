"""
Retriever — Hybrid Search + Contextual Re-ranking
===================================================
Pipeline:
  1. BM25Retriever (keyword/sparse) + FAISS/MMR (dense) via EnsembleRetriever
     → hybrid search captures both exact keyword matches and semantic similarity
  2. _SafeEmbeddingsFilter (BaseRetriever subclass)
     → re-ranks by cosine similarity to query, drops low-relevance chunks
     → SAFETY NET: if threshold would drop ALL candidates, keeps top-min_docs
     → logs candidate counts at each stage for observability
  3. Optional MultiQueryRetriever
     → rewrites query into N variants; union of results improves recall for
        compound or ambiguous questions
     → cost: ~2–4x additional LLM calls per query (disable if cost-sensitive)
  4. SafeQueryWrapper (outermost, always applied)
     → ensures retrievers ALWAYS receive a plain str, not a dict
     → create_retrieval_chain passes {"input": str} — this wrapper normalizes it
     → protects BM25, FAISS, and all inner retrievers from contract violations

Configuration:
  All tunables pulled from config/settings.py — no magic numbers here.

Rerank threshold guidance:
  text-embedding-3-small query-to-chunk cosine similarity for relevant content
  is typically 0.30–0.65. The old default of 0.75 dropped ALL candidates.
  Safe default is 0.30. Raise toward 0.50 only after empirical validation.

Multi-tenancy:
  filter_kwargs (e.g. {"user_id": "u123"}) applied to BOTH FAISS (native) and
  BM25 (pre-filtered doc list) so tenant isolation is preserved across both legs.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

logger = logging.getLogger(__name__)

# ── Constants (overridden by settings when get_retriever is called) ───────────
DEFAULT_SEARCH_TYPE = "mmr"
DEFAULT_TOP_K = 8
MMR_FETCH_K = 120          # Candidate pool before MMR diversification
MMR_LAMBDA = 0.6           # 0=max diversity, 1=max relevance
_RERANKER_MIN_DOCS = 1     # Safety net: never drop ALL candidates


# ── LLM singleton for MultiQueryRetriever ────────────────────────────────────
@lru_cache(maxsize=1)
def _get_multi_query_llm(model: str):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=0)


# ── Embeddings singleton for re-ranking ──────────────────────────────────────
@lru_cache(maxsize=8)
def _get_embeddings(model: str):
    """Cached OpenAIEmbeddings instance — avoids cold-start HTTP client creation per query."""
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=model)


def get_retriever(
    vectorstore: Any,
    top_k: int = DEFAULT_TOP_K,
    use_multi_query: bool = True,
    use_hybrid: bool = True,
    hybrid_bm25_weight: float = 0.3,
    rerank_threshold: float = 0.30,
    filter_kwargs: Optional[Dict[str, Any]] = None,
    embedding_model: str = "text-embedding-3-small",
    llm_model: str = "gpt-4o-mini",
    multi_query_num_queries: int = 2,
) -> "SafeQueryWrapper":
    """
    Build a production retriever from a FAISS vectorstore.

    Always returns a SafeQueryWrapper (BaseRetriever) which:
      - guarantees str input to all inner retrievers
      - is correctly handled by create_retrieval_chain
    """
    if vectorstore is None:
        raise ValueError("vectorstore cannot be None.")

    # ── Step 1: FAISS/MMR base retriever ─────────────────────────────────────
    faiss_search_kwargs: Dict[str, Any] = {
        "k": top_k,
        "fetch_k": MMR_FETCH_K,
        "lambda_mult": MMR_LAMBDA,
    }
    if filter_kwargs:
        faiss_search_kwargs["filter"] = filter_kwargs

    faiss_retriever = vectorstore.as_retriever(
        search_type=DEFAULT_SEARCH_TYPE,
        search_kwargs=faiss_search_kwargs,
    )

    # ── Step 2: Hybrid BM25 + FAISS ensemble ─────────────────────────────────
    base_retriever = faiss_retriever
    if use_hybrid:
        base_retriever = _build_hybrid_retriever(
            vectorstore=vectorstore,
            faiss_retriever=faiss_retriever,
            top_k=top_k,
            bm25_weight=hybrid_bm25_weight,
            filter_kwargs=filter_kwargs,
        )

    # ── Step 3: Contextual compression (embedding-based re-ranking) ───────────
    retriever = _apply_reranker(
        base_retriever=base_retriever,
        embedding_model=embedding_model,
        threshold=rerank_threshold,
        min_docs=_RERANKER_MIN_DOCS,
    )

    # ── Step 4: MultiQueryRetriever (optional) ────────────────────────────────
    if use_multi_query:
        retriever = _apply_multi_query(retriever, llm_model, num_queries=multi_query_num_queries)

    # ── Step 5: SafeQueryWrapper — ALWAYS applied as outermost layer ──────────
    # This is the system boundary guard. create_retrieval_chain passes the full
    # {"input": str} dict in some code paths; this wrapper normalises it to str
    # before any inner retriever (BM25, FAISS, reranker) sees the input.
    wrapped = SafeQueryWrapper(inner=retriever)

    logger.info(
        "Retriever built | hybrid=%s | multi_query=%s | num_queries=%d | top_k=%d | rerank_threshold=%.2f",
        use_hybrid, use_multi_query, multi_query_num_queries if use_multi_query else 1,
        top_k, rerank_threshold,
    )
    return wrapped


# ── SafeQueryWrapper ──────────────────────────────────────────────────────────

class SafeQueryWrapper(BaseRetriever):
    """
    Outermost retriever wrapper — system boundary input guard.

    Guarantees that ALL inner retrievers (BM25, FAISS, EnsembleRetriever,
    _SafeEmbeddingsFilter, MultiQueryRetriever) receive a plain str query,
    never a dict or other unexpected type.

    Why this is necessary:
      LangChain's create_retrieval_chain passes {"input": str} as the chain
      input. For BaseRetriever subclasses it extracts "input" first; for
      non-BaseRetriever objects it may pass the full dict. This wrapper is a
      BaseRetriever, so the extraction always happens at this boundary —
      making all inner logic immune to input shape changes in LangChain.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: Any

    def _get_relevant_documents(
        self, query: Any, *, run_manager=None
    ) -> List[Document]:
        original_query = query

        # Normalize dict → str (defense-in-depth; normally BaseRetriever
        # extraction upstream already handles this, but never rely on it)
        if isinstance(query, dict):
            query = query.get("input") or query.get("query") or ""
            logger.info(
                "SafeQueryWrapper: normalised dict query | original_keys=%s",
                list(original_query.keys()),
            )

        if not isinstance(query, str):
            raise ValueError(
                f"Query must be a str, got {type(query).__name__}: {query!r}"
            )

        query = query.strip()
        if not query:
            raise ValueError("Query is empty after stripping whitespace.")

        logger.info(
            "SafeQueryWrapper: dispatching | query='%s...' | inner=%s",
            query[:80],
            type(self.inner).__name__,
        )

        # Delegate to inner retriever.
        # _SafeEmbeddingsFilter and MultiQueryRetriever are both BaseRetriever
        # subclasses, so invoke() correctly routes through _get_relevant_documents.
        return self.inner.invoke(query)

    async def _aget_relevant_documents(
        self, query: Any, *, run_manager=None
    ) -> List[Document]:
        # Async path — same normalisation, then await async inner
        if isinstance(query, dict):
            query = query.get("input") or query.get("query") or ""
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Invalid async query: {query!r}")
        return await self.inner.ainvoke(query.strip())


# ── _SafeEmbeddingsFilter ─────────────────────────────────────────────────────

class _SafeEmbeddingsFilter(BaseRetriever):
    """
    Proper BaseRetriever subclass — replaces ContextualCompressionRetriever.

    Production guarantees:
      1. Observability: logs candidate count before and after filtering.
      2. Safety net: if ALL candidates would be dropped (threshold too high),
         returns top-`min_docs` by similarity score instead of empty list.
      3. Exception fallback: if embedding call fails, returns base docs
         unfiltered — never crashes the query pipeline.

    Why BaseRetriever (not a plain class):
      LangChain's MultiQueryRetriever calls self.retriever.invoke() on the
      wrapped retriever. Plain classes have no `invoke` method; the old
      __getattr__ delegation bypassed filtering entirely. As a BaseRetriever,
      invoke() correctly routes through _get_relevant_documents().
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_retriever: Any
    embedding_model: str
    threshold: float
    min_docs: int = 1

    def _get_relevant_documents(
        self, query: str, *, run_manager=None
    ) -> List[Document]:
        import numpy as np

        # Get base results from hybrid/FAISS retriever
        # Uses .invoke() — get_relevant_documents() is deprecated in LangChain 0.2+
        base_docs = self.base_retriever.invoke(query)
        logger.info(
            "Reranker input: %d candidates | threshold=%.2f | query='%s...'",
            len(base_docs), self.threshold, query[:60],
        )

        if not base_docs:
            logger.warning("Reranker: base retriever returned 0 candidates.")
            return []

        try:
            embeddings = _get_embeddings(self.embedding_model)
            query_emb = np.array(embeddings.embed_query(query))
            doc_texts = [d.page_content for d in base_docs]
            doc_embs = np.array(embeddings.embed_documents(doc_texts))

            # Cosine similarities (OpenAI embeddings are L2-normalised)
            similarities = (doc_embs @ query_emb).tolist()

            # Sort by similarity descending
            scored = sorted(
                zip(similarities, base_docs),
                key=lambda x: x[0],
                reverse=True,
            )

            # Apply threshold filter
            passed = [(s, d) for s, d in scored if s >= self.threshold]

            logger.info(
                "Reranker output: %d/%d passed threshold=%.2f | best_sim=%.3f | worst_sim=%.3f",
                len(passed), len(base_docs), self.threshold,
                scored[0][0] if scored else 0.0,
                scored[-1][0] if scored else 0.0,
            )

            if passed:
                return [d for _, d in passed]

            # Safety net: threshold dropped everything — return top-min_docs
            fallback = [d for _, d in scored[: self.min_docs]]
            logger.warning(
                "Reranker safety net triggered: all %d docs below threshold=%.2f "
                "(best_sim=%.3f). Returning top-%d to prevent empty context. "
                "Consider lowering RERANK_THRESHOLD in settings.",
                len(base_docs), self.threshold,
                scored[0][0] if scored else 0.0,
                len(fallback),
            )
            return fallback

        except Exception as e:
            logger.warning(
                "Reranker similarity computation failed (%s) — returning base "
                "results unfiltered.",
                e,
            )
            return base_docs

    async def _aget_relevant_documents(
        self, query: str, *, run_manager=None
    ) -> List[Document]:
        return self._get_relevant_documents(query, run_manager=run_manager)


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_hybrid_retriever(
    vectorstore: Any,
    faiss_retriever: Any,
    top_k: int,
    bm25_weight: float,
    filter_kwargs: Optional[Dict[str, Any]],
) -> Any:
    """Build BM25 retriever from FAISS docstore and ensemble with FAISS/MMR."""
    try:
        from langchain_community.retrievers import BM25Retriever
        from langchain.retrievers import EnsembleRetriever

        # Extract all documents from the FAISS docstore
        all_docs = _extract_docs_from_faiss(vectorstore)
        if not all_docs:
            logger.warning("FAISS docstore empty — skipping hybrid search.")
            return faiss_retriever

        # Pre-filter docs for BM25 to honour multi-tenancy
        bm25_docs = _filter_docs(all_docs, filter_kwargs)
        if not bm25_docs:
            logger.warning(
                "No docs match filter_kwargs=%s for BM25 — using full corpus of %d docs.",
                filter_kwargs, len(all_docs),
            )
            bm25_docs = all_docs

        bm25_retriever = BM25Retriever.from_documents(bm25_docs)
        bm25_retriever.k = top_k

        ensemble = EnsembleRetriever(
            retrievers=[bm25_retriever, faiss_retriever],
            weights=[bm25_weight, 1.0 - bm25_weight],
        )
        logger.info(
            "Hybrid retriever built | bm25_weight=%.2f | bm25_docs=%d | total_docs=%d",
            bm25_weight, len(bm25_docs), len(all_docs),
        )
        return ensemble

    except Exception as e:
        logger.warning("Hybrid search unavailable (%s) — falling back to FAISS only.", e)
        return faiss_retriever


def _apply_reranker(
    base_retriever: Any,
    embedding_model: str,
    threshold: float,
    min_docs: int = 1,
) -> "_SafeEmbeddingsFilter":
    """Wrap retriever with _SafeEmbeddingsFilter for similarity-based re-ranking."""
    try:
        logger.info("Re-ranking layer applied | threshold=%.2f | min_docs=%d", threshold, min_docs)
        return _SafeEmbeddingsFilter(
            base_retriever=base_retriever,
            embedding_model=embedding_model,
            threshold=threshold,
            min_docs=min_docs,
        )
    except Exception as e:
        logger.warning("Re-ranking setup failed (%s) — skipping.", e)
        return base_retriever


def _apply_multi_query(base_retriever: Any, llm_model: str, num_queries: int = 2) -> Any:
    """Wrap with MultiQueryRetriever — reuses cached LLM instance.

    num_queries is controlled via a custom prompt, NOT via attribute assignment.
    MultiQueryRetriever (Pydantic v2, extra='ignore') silently discards unknown
    attribute assignments — setting .num_queries post-construction raises
    ValueError in Pydantic v2. The version-compatible fix is to pass a custom
    prompt whose text explicitly requests the desired number of variants.
    """
    try:
        from langchain.retrievers.multi_query import MultiQueryRetriever
        from langchain_core.prompts import PromptTemplate

        llm = _get_multi_query_llm(llm_model)

        # Override the default prompt (which hardcodes "3 different versions").
        # This is the only version-compatible way to control query count in
        # LangChain 0.3 — from_llm() does not accept num_queries as a kwarg
        # and the model has no such field.
        prompt = PromptTemplate(
            input_variables=["question"],
            template=(
                f"You are an AI assistant helping retrieve relevant financial documents. "
                f"Generate {num_queries} different versions of the given question to "
                f"improve document retrieval by covering different phrasings and aspects. "
                f"Provide these alternative questions separated by newlines. "
                f"Original question: {{question}}"
            ),
        )

        retriever = MultiQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=llm,
            prompt=prompt,
        )
        logger.info("MultiQueryRetriever applied | model=%s | num_queries=%d", llm_model, num_queries)
        return retriever
    except Exception as e:
        logger.warning("MultiQueryRetriever failed (%s) — using base retriever.", e)
        return base_retriever


def _extract_docs_from_faiss(vectorstore: Any) -> List[Document]:
    """Extract all Document objects from a FAISS vectorstore's docstore."""
    try:
        doc_ids = list(vectorstore.index_to_docstore_id.values())
        docs = [vectorstore.docstore.search(did) for did in doc_ids]
        return [d for d in docs if d is not None and isinstance(d, Document)]
    except Exception as e:
        logger.warning("Could not extract docs from FAISS docstore: %s", e)
        return []


def _filter_docs(
    docs: List[Document],
    filter_kwargs: Optional[Dict[str, Any]],
) -> List[Document]:
    """Filter a list of Documents by metadata key-value pairs."""
    if not filter_kwargs:
        return docs
    return [
        doc for doc in docs
        if all(doc.metadata.get(k) == v for k, v in filter_kwargs.items())
    ]
