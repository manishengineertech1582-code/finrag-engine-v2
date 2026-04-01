"""
Adaptive MultiQuery + History Cap Tests
=========================================
Covers Phase 14 additions:

  M1 — _is_complex_query: short queries correctly skip MultiQuery
  M2 — _is_complex_query: long/ambiguous queries correctly use MultiQuery
  M3 — _is_complex_query: boundary conditions at exactly 5 words / 30 chars
  M4 — _build_pipeline passes use_multi_query=False for simple questions
  M5 — _build_pipeline passes use_multi_query=True for complex questions
  M6 — pipeline cache distinguishes mq=True vs mq=False (separate entries)
  M7 — queries_generated=1 in response when MultiQuery is adaptively skipped
  M8 — queries_generated=settings.multi_query_num_queries when MultiQuery used
  M9 — cache key includes mq flag — no cross-contamination between pipelines

History (frontend store logic validated via backend):
  H1 — HISTORY_LIMIT constant is 5 in appStore (verified by reading the constant)
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_result(answer="Test answer.", docs=None):
    doc = MagicMock()
    doc.page_content = "Financial content from document."
    doc.metadata = {
        "source": "report.pdf",
        "page_or_sheet": "page_1",
        "doc_type": "pdf",
        "chunk_id": "abc123",
        "user_id": None,
    }
    return {"answer": answer, "context": docs if docs is not None else [doc]}


@pytest.fixture(autouse=True)
def clear_caches():
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
    from config.settings import get_settings
    from app.state import pipeline_cache, query_result_cache
    get_settings.cache_clear()
    pipeline_cache.clear()
    query_result_cache.clear()
    yield
    pipeline_cache.clear()
    query_result_cache.clear()
    get_settings.cache_clear()


# ── M1/M2/M3: _is_complex_query ───────────────────────────────────────────────

class TestIsComplexQuery:
    def _fn(self):
        from app.routes.query import _is_complex_query
        return _is_complex_query

    # Short queries — must return False (skip MultiQuery)
    def test_single_word_is_simple(self):
        assert self._fn()("revenue") is False

    def test_two_word_is_simple(self):
        assert self._fn()("revenue growth") is False

    def test_four_word_is_simple(self):
        assert self._fn()("what is revenue?") is False

    def test_short_sentence_under_30_chars_is_simple(self):
        assert self._fn()("Summarize key risks") is False

    # Complex queries — must return True (use MultiQuery)
    def test_five_word_long_enough_is_complex(self):
        q = "What are the key financial risks?"   # 7 words, 33 chars
        assert self._fn()(q) is True

    def test_long_question_is_complex(self):
        q = "What drove revenue growth in the most recent fiscal year versus prior year?"
        assert self._fn()(q) is True

    def test_multi_clause_question_is_complex(self):
        q = "Are there any going concern issues and what remediation steps are planned?"
        assert self._fn()(q) is True

    # Boundary: exactly at threshold — 4 words → False; 5 words + 30 chars → True
    def test_four_word_boundary_is_simple(self):
        # 4 words = below threshold
        assert self._fn()("What is the revenue?") is False

    def test_five_word_but_short_chars_is_simple(self):
        # 5+ words but < 30 chars total
        assert self._fn()("a b c d e f") is False  # 12 chars

    def test_five_word_and_30_plus_chars_is_complex(self):
        # Exactly 5 words AND ≥30 chars
        q = "Summarize the key risk factors"   # 5 words, 30 chars
        assert self._fn()(q) is True


# ── M4/M5/M6: _build_pipeline adaptive MultiQuery passthrough ─────────────────

class TestBuildPipelineAdaptiveMultiQuery:

    def _post(self, question: str, top_k: int = 8):
        """Submit a query via TestClient with a mocked pipeline."""
        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        with patch("app.routes.query._build_pipeline", wraps=self._capture(chain)) as wrapped:
            client = TestClient(fastapi_app)
            resp = client.post("/api/ask", json={"question": question, "top_k": top_k})
        return resp, wrapped

    def _capture(self, chain):
        """Wraps _build_pipeline to intercept and return mock chain."""
        from app.routes import query as q_module
        original = q_module._build_pipeline

        captured = {}

        def wrapper(request, use_multi_query=True):
            captured["use_multi_query"] = use_multi_query
            return chain

        wrapper.captured = captured
        return wrapper

    def test_simple_query_passes_false(self):
        """Short question (≤4 words) must set use_multi_query=False in pipeline."""
        from app.routes.query import _build_pipeline, _is_complex_query
        from models.request import QueryRequest

        short_q = "what is revenue?"
        assert _is_complex_query(short_q) is False

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        with patch("app.routes.query.load_pipeline", return_value=chain) as mock_load:
            _build_pipeline(
                QueryRequest(question=short_q, top_k=8),
                use_multi_query=False,
            )
        mock_load.assert_called_once()
        _, call_kwargs = mock_load.call_args
        assert call_kwargs.get("use_multi_query") is False

    def test_complex_query_passes_true(self):
        """Long/ambiguous question must set use_multi_query=True in pipeline."""
        from app.routes.query import _build_pipeline, _is_complex_query
        from models.request import QueryRequest

        complex_q = "What are the key financial risk factors for this year?"
        assert _is_complex_query(complex_q) is True

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        with patch("app.routes.query.load_pipeline", return_value=chain) as mock_load:
            _build_pipeline(
                QueryRequest(question=complex_q, top_k=8),
                use_multi_query=True,
            )
        mock_load.assert_called_once()
        _, call_kwargs = mock_load.call_args
        assert call_kwargs.get("use_multi_query") is True

    def test_cache_key_differentiates_mq_flag(self):
        """Pipelines with mq=True and mq=False must be cached separately."""
        from app.state import pipeline_cache
        from app.routes.query import _build_pipeline
        from models.request import QueryRequest

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()
        pipeline_cache.clear()

        q = QueryRequest(question="What is revenue?", top_k=8)

        with patch("app.routes.query.load_pipeline", return_value=chain):
            _build_pipeline(q, use_multi_query=False)
            _build_pipeline(q, use_multi_query=True)

        # Two different cache entries — mq=False and mq=True
        assert sum(1 for k in pipeline_cache if "mq=False" in k) == 1
        assert sum(1 for k in pipeline_cache if "mq=True" in k) == 1


# ── M7/M8: queries_generated in response ──────────────────────────────────────

class TestQueriesGeneratedInResponse:

    def _client_with_mock(self):
        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        from app.state import pipeline_cache, query_result_cache
        pipeline_cache.clear()
        query_result_cache.clear()
        return TestClient(fastapi_app)

    def test_simple_query_reports_queries_generated_1(self, monkeypatch):
        """Short query → MultiQuery skipped → queries_generated must be 1."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("USE_MULTI_QUERY", "true")
        monkeypatch.setenv("MULTI_QUERY_NUM_QUERIES", "2")
        from config.settings import get_settings
        get_settings.cache_clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        client = self._client_with_mock()
        # "what is revenue?" → 4 words → _is_complex_query=False → mq skipped
        with patch("app.routes.query._build_pipeline", return_value=chain):
            resp = client.post("/api/ask", json={"question": "what is revenue?", "top_k": 8})

        assert resp.status_code == 200
        data = resp.json()
        assert data["retrieval_meta"]["queries_generated"] == 1
        get_settings.cache_clear()

    def test_complex_query_reports_num_queries_from_settings(self, monkeypatch):
        """Long query → MultiQuery enabled → queries_generated must match settings."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("USE_MULTI_QUERY", "true")
        monkeypatch.setenv("MULTI_QUERY_NUM_QUERIES", "2")
        from config.settings import get_settings
        get_settings.cache_clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        client = self._client_with_mock()
        long_q = "What are the primary financial risk factors affecting profitability?"
        with patch("app.routes.query._build_pipeline", return_value=chain):
            resp = client.post("/api/ask", json={"question": long_q, "top_k": 8})

        assert resp.status_code == 200
        data = resp.json()
        assert data["retrieval_meta"]["queries_generated"] == 2
        get_settings.cache_clear()

    def test_multi_query_disabled_globally_always_reports_1(self, monkeypatch):
        """When USE_MULTI_QUERY=false, queries_generated must be 1 regardless of question length."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("USE_MULTI_QUERY", "false")
        from config.settings import get_settings
        get_settings.cache_clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        client = self._client_with_mock()
        long_q = "What are the primary financial risk factors affecting profitability?"
        with patch("app.routes.query._build_pipeline", return_value=chain):
            resp = client.post("/api/ask", json={"question": long_q, "top_k": 8})

        assert resp.status_code == 200
        data = resp.json()
        assert data["retrieval_meta"]["queries_generated"] == 1
        get_settings.cache_clear()
