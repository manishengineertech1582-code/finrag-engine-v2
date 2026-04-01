"""
Retrieval Pipeline Regression Tests
=====================================
Guards against two classes of production failures:

RCA-4 — BM25 dict crash
  SafeQueryWrapper must normalise dict inputs so BM25 never receives {"input": ...}
  and crashes on .split().

RCA-5 — Reranker bypass
  _SafeEmbeddingsFilter is now a BaseRetriever subclass so MultiQueryRetriever's
  .invoke() correctly routes through _get_relevant_documents (filtering logic)
  instead of delegating via __getattr__ to the base retriever directly.
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_doc(content: str = "test content", **meta) -> Document:
    return Document(page_content=content, metadata=meta)


def _make_mock_inner(docs: list | None = None) -> MagicMock:
    """Return a mock retriever whose .invoke() and .get_relevant_documents() return docs."""
    mock = MagicMock()
    docs = docs or [_make_doc("result")]
    mock.invoke.return_value = docs
    mock.get_relevant_documents.return_value = docs
    return mock


# ── SafeQueryWrapper ──────────────────────────────────────────────────────────

class TestSafeQueryWrapper:
    """Contract tests for the outermost query normalisation layer."""

    def _make_wrapper(self, docs=None):
        from src.retriever import SafeQueryWrapper
        return SafeQueryWrapper(inner=_make_mock_inner(docs))

    # ── Input normalisation ────────────────────────────────────────────────

    def test_dict_input_normalised_to_string(self):
        """Dict with 'input' key must be extracted to plain str before dispatch."""
        wrapper = self._make_wrapper()
        result = wrapper.invoke({"input": "what is revenue?"})
        # Inner mock must have been called with the plain string
        wrapper.inner.invoke.assert_called_once_with("what is revenue?")
        assert isinstance(result, list)

    def test_dict_input_with_query_key_normalised(self):
        """Dict with 'query' key (alternative LangChain key) also normalised."""
        wrapper = self._make_wrapper()
        result = wrapper.invoke({"query": "summarise document"})
        wrapper.inner.invoke.assert_called_once_with("summarise document")
        assert isinstance(result, list)

    def test_string_input_passed_through_unchanged(self):
        """Plain string must reach the inner retriever as-is."""
        wrapper = self._make_wrapper()
        result = wrapper.invoke("plain string query")
        wrapper.inner.invoke.assert_called_once_with("plain string query")
        assert isinstance(result, list)

    def test_string_with_surrounding_whitespace_stripped(self):
        """Leading/trailing whitespace in query is stripped before dispatch."""
        wrapper = self._make_wrapper()
        wrapper.invoke("  spaced query  ")
        wrapper.inner.invoke.assert_called_once_with("spaced query")

    # ── Error cases ────────────────────────────────────────────────────────

    def test_integer_input_raises_value_error(self):
        """Non-str, non-dict inputs must raise ValueError immediately."""
        wrapper = self._make_wrapper()
        with pytest.raises(ValueError, match="str"):
            wrapper.invoke(42)

    def test_none_input_raises_value_error(self):
        wrapper = self._make_wrapper()
        with pytest.raises(ValueError):
            wrapper.invoke(None)

    def test_empty_string_raises_value_error(self):
        """Empty string (after stripping) must raise — cannot produce useful results."""
        wrapper = self._make_wrapper()
        with pytest.raises(ValueError, match="empty"):
            wrapper.invoke("")

    def test_whitespace_only_string_raises_value_error(self):
        wrapper = self._make_wrapper()
        with pytest.raises(ValueError, match="empty"):
            wrapper.invoke("   ")

    def test_empty_dict_raises_value_error(self):
        """Dict without 'input' or 'query' key produces empty string → ValueError."""
        wrapper = self._make_wrapper()
        with pytest.raises(ValueError):
            wrapper.invoke({})

    # ── Output contract ────────────────────────────────────────────────────

    def test_returns_list_of_documents(self):
        docs = [_make_doc("doc1"), _make_doc("doc2")]
        wrapper = self._make_wrapper(docs)
        result = wrapper.invoke("valid query")
        assert result == docs

    def test_is_base_retriever_subclass(self):
        """SafeQueryWrapper must be a BaseRetriever so create_retrieval_chain
        handles it correctly (extracting 'input' before invocation)."""
        from src.retriever import SafeQueryWrapper
        from langchain_core.retrievers import BaseRetriever
        assert issubclass(SafeQueryWrapper, BaseRetriever)

    def test_invoke_also_normalises_dict(self):
        """invoke() is the LangChain-preferred call path — must also normalise."""
        from src.retriever import SafeQueryWrapper
        wrapper = SafeQueryWrapper(inner=_make_mock_inner())
        result = wrapper.invoke({"input": "via invoke"})
        # After BaseRetriever.invoke extracts the string, _get_relevant_documents
        # receives a str. The inner mock should be called.
        assert isinstance(result, list)


# ── _SafeEmbeddingsFilter ─────────────────────────────────────────────────────

class TestSafeEmbeddingsFilterAsBaseRetriever:
    """
    _SafeEmbeddingsFilter must be a BaseRetriever so that MultiQueryRetriever's
    .invoke() correctly routes through _get_relevant_documents (not __getattr__).
    """

    def test_is_base_retriever_subclass(self):
        from src.retriever import _SafeEmbeddingsFilter
        from langchain_core.retrievers import BaseRetriever
        assert issubclass(_SafeEmbeddingsFilter, BaseRetriever)

    def test_invoke_routes_through_filtering_logic(self):
        """
        invoke() must call _get_relevant_documents (which contains reranking),
        NOT delegate to base_retriever.invoke via __getattr__.
        This was the RCA-5 bug: filtering was silently bypassed.
        """
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        docs = [_make_doc("chunk 1"), _make_doc("chunk 2")]
        # Phase 12: code now calls base.invoke() (not deprecated get_relevant_documents)
        base.invoke.return_value = docs

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.99,  # impossibly high → safety net must trigger
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [1.0, 0.0]
        mock_emb.embed_documents.return_value = [
            [0.5, 0.0],  # both below 0.99
            [0.4, 0.0],
        ]
        # Patch _get_embeddings directly so lru_cache doesn't interfere
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            # Call via .invoke() — this is what MultiQueryRetriever uses
            result = filt.invoke("some query")

        # Phase 12: base.invoke() must have been called, NOT get_relevant_documents
        base.invoke.assert_called_once()
        base.get_relevant_documents.assert_not_called()
        # Result must be non-empty (safety net)
        assert len(result) >= 1

    def test_safety_net_never_returns_empty(self):
        """When all docs are below threshold, safety net returns top-min_docs."""
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        docs = [_make_doc(f"doc {i}") for i in range(3)]
        base.invoke.return_value = docs  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.99,
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [1.0, 0.0]
        mock_emb.embed_documents.return_value = [
            [0.3, 0.0],
            [0.2, 0.0],
            [0.1, 0.0],
        ]
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("query")

        assert len(result) >= 1, "Safety net must prevent empty context"

    def test_empty_base_results_returns_empty_without_crash(self):
        """If the base retriever returns nothing, return [] without crashing."""
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        base.invoke.return_value = []  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.30,
            min_docs=1,
        )

        mock_emb = MagicMock()
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("query")

        assert result == []

    def test_embedding_exception_returns_base_docs_unfiltered(self):
        """If embedding call fails, fall back to base docs (no crash)."""
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        docs = [_make_doc("fallback content")]
        base.invoke.return_value = docs  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.30,
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.side_effect = RuntimeError("API down")
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("query")

        assert result == docs, "Fallback must return base docs when embedding fails"

    def test_docs_above_threshold_returned(self):
        """Docs above threshold are returned; docs below are filtered out."""
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        high_doc = _make_doc("highly relevant")
        low_doc = _make_doc("totally unrelated")
        base.invoke.return_value = [high_doc, low_doc]  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.50,
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [1.0, 0.0]
        mock_emb.embed_documents.return_value = [
            [0.80, 0.0],  # high_doc — above 0.50 ✓
            [0.20, 0.0],  # low_doc  — below 0.50 ✗
        ]
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("relevant query")

        # Only high_doc passes; low_doc filtered out
        assert len(result) == 1
        assert result[0].page_content == "highly relevant"


# ── get_retriever integration ─────────────────────────────────────────────────

class TestGetRetrieverContract:
    """get_retriever() must always return a SafeQueryWrapper (BaseRetriever)."""

    def test_returns_safe_query_wrapper(self):
        from src.retriever import get_retriever, SafeQueryWrapper

        mock_vs = MagicMock()
        # Provide enough docstore structure for hybrid path
        mock_vs.index_to_docstore_id = {}

        retriever = get_retriever(
            vectorstore=mock_vs,
            top_k=4,
            use_multi_query=False,
            use_hybrid=False,
        )
        assert isinstance(retriever, SafeQueryWrapper), (
            "get_retriever() must always return SafeQueryWrapper; "
            "create_retrieval_chain requires a BaseRetriever to extract the "
            "'input' key before passing the query to inner retrievers."
        )

    def test_raises_on_none_vectorstore(self):
        from src.retriever import get_retriever
        with pytest.raises(ValueError, match="None"):
            get_retriever(vectorstore=None)


# ── _filter_docs ───────────────────────────────────────────────────────────────

class TestFilterDocs:
    def test_no_filter_returns_all(self):
        from src.retriever import _filter_docs
        docs = [
            Document(page_content="a", metadata={"user_id": "u1"}),
            Document(page_content="b", metadata={"user_id": "u2"}),
        ]
        assert _filter_docs(docs, None) == docs

    def test_user_id_filter_isolates_correctly(self):
        from src.retriever import _filter_docs
        docs = [
            Document(page_content="u1 doc", metadata={"user_id": "u1"}),
            Document(page_content="u2 doc", metadata={"user_id": "u2"}),
            Document(page_content="u1 doc2", metadata={"user_id": "u1"}),
        ]
        result = _filter_docs(docs, {"user_id": "u1"})
        assert len(result) == 2
        assert all(d.metadata["user_id"] == "u1" for d in result)

    def test_no_match_returns_empty(self):
        from src.retriever import _filter_docs
        docs = [Document(page_content="x", metadata={"user_id": "u1"})]
        assert _filter_docs(docs, {"user_id": "u999"}) == []
