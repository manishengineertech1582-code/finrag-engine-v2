"""
Pipeline Loader
===============
Assembles the retriever and QA chain from the shared configuration.
"""

import logging
from typing import Any, Tuple

from config.settings import get_settings
from src.embeddings import load_vector_store
from src.generator import build_qa_chain
from src.retriever import get_retriever

logger = logging.getLogger(__name__)


def _resolve_pipeline_options(
    vectorstore_path: str | None = None,
    top_k: int | None = None,
    use_multi_query: bool | None = None,
) -> Tuple[Any, str, int, bool]:
    settings = get_settings()
    path = vectorstore_path or settings.vectorstore_path
    effective_top_k = top_k if top_k is not None else settings.top_k
    effective_multi_query = (
        use_multi_query if use_multi_query is not None else settings.use_multi_query
    )
    return settings, path, effective_top_k, effective_multi_query


def _load_retriever(
    *,
    settings: Any,
    path: str,
    top_k: int,
    use_multi_query: bool,
    filter_kwargs: dict | None = None,
):
    logger.info("Loading vector store | path=%s", path)
    vectorstore = load_vector_store(
        persist_path=path,
        embedding_model=settings.embedding_model,
    )

    logger.info(
        "Building retriever | top_k=%d | hybrid=%s | multi_query=%s | num_queries=%d",
        top_k,
        settings.use_hybrid_search,
        use_multi_query,
        settings.multi_query_num_queries,
    )
    return get_retriever(
        vectorstore=vectorstore,
        top_k=top_k,
        use_multi_query=use_multi_query,
        use_hybrid=settings.use_hybrid_search,
        hybrid_bm25_weight=settings.hybrid_bm25_weight,
        rerank_threshold=settings.rerank_threshold,
        filter_kwargs=filter_kwargs,
        embedding_model=settings.embedding_model,
        llm_model=settings.openai_model,
        multi_query_num_queries=settings.multi_query_num_queries,
    )


def load_retriever_only(
    vectorstore_path: str | None = None,
    top_k: int | None = None,
    use_multi_query: bool | None = None,
    filter_kwargs: dict | None = None,
):
    """Load only the retriever for retrieval-first orchestration paths."""
    settings, path, effective_top_k, effective_multi_query = _resolve_pipeline_options(
        vectorstore_path=vectorstore_path,
        top_k=top_k,
        use_multi_query=use_multi_query,
    )
    retriever = _load_retriever(
        settings=settings,
        path=path,
        top_k=effective_top_k,
        use_multi_query=effective_multi_query,
        filter_kwargs=filter_kwargs,
    )
    logger.info("Retriever ready.")
    return retriever


def load_pipeline(
    vectorstore_path: str | None = None,
    top_k: int | None = None,
    use_multi_query: bool | None = None,
    filter_kwargs: dict | None = None,
):
    """Load and assemble the complete retrieval + generation pipeline."""
    settings, path, effective_top_k, effective_multi_query = _resolve_pipeline_options(
        vectorstore_path=vectorstore_path,
        top_k=top_k,
        use_multi_query=use_multi_query,
    )

    retriever = _load_retriever(
        settings=settings,
        path=path,
        top_k=effective_top_k,
        use_multi_query=effective_multi_query,
        filter_kwargs=filter_kwargs,
    )

    logger.info("Building QA chain | model=%s", settings.openai_model)
    qa_chain = build_qa_chain(
        retriever=retriever,
        model=settings.openai_model,
        max_tokens=settings.answer_max_tokens,
    )

    logger.info("Pipeline ready.")
    return qa_chain
