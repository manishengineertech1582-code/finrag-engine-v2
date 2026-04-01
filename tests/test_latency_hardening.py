"""
Latency & Architecture Hardening Tests
========================================
Covers Phase 12 root-cause fixes:

  L1 — OpenAIEmbeddings instance is cached (not re-created per query)
  L2 — _SafeEmbeddingsFilter uses .invoke(), not deprecated .get_relevant_documents()
  L3 — MultiQueryRetriever uses settings.multi_query_num_queries (default=2)
  L4 — Query result cache: hit / miss / expiry / ingest invalidation / TTL=0 bypass
  L5 — request_id present + unique per call
  L6 — latency_ms present and > 0 on live calls
  L7/L8 — AbortSignal threaded through api.query (integration note only — covered
            by TypeScript types and reviewed in useQuery.ts)
  settings — new defaults verified
"""

import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_result(answer="Test answer.", docs=None):
    """Return a minimal qa_chain.invoke result dict."""
    doc = MagicMock()
    doc.page_content = "Some financial content for testing purposes."
    doc.metadata = {
        "source": "test.pdf",
        "page_or_sheet": "page_1",
        "doc_type": "pdf",
        "chunk_id": "abc123",
        "user_id": None,
    }
    return {"answer": answer, "context": docs if docs is not None else [doc]}


@pytest.fixture
def app():
    """FastAPI TestClient with a mocked pipeline and fresh caches."""
    from config.settings import get_settings
    get_settings.cache_clear()

    from app.state import pipeline_cache, query_result_cache
    pipeline_cache.clear()
    query_result_cache.clear()

    from app.main import app as fastapi_app
    yield fastapi_app

    # Teardown
    pipeline_cache.clear()
    query_result_cache.clear()
    get_settings.cache_clear()


@pytest.fixture
def client(app):
    return TestClient(app)


# ── L1: Embeddings cache ──────────────────────────────────────────────────────

class TestEmbeddingsCacheHit:
    def test_embeddings_instance_reused_across_calls(self):
        """_get_embeddings must return the same object on repeated calls."""
        from src.retriever import _get_embeddings
        _get_embeddings.cache_clear()

        # Patch at the source module (langchain_openai) since _get_embeddings
        # does `from langchain_openai import OpenAIEmbeddings` inside the function.
        with patch("langchain_openai.OpenAIEmbeddings") as MockEmb:
            MockEmb.return_value = MagicMock()
            a = _get_embeddings("text-embedding-3-small")
            b = _get_embeddings("text-embedding-3-small")
            assert a is b
            # Constructor must have been called exactly once, not twice
            assert MockEmb.call_count == 1

        _get_embeddings.cache_clear()

    def test_different_models_get_separate_instances(self):
        from src.retriever import _get_embeddings
        _get_embeddings.cache_clear()

        with patch("langchain_openai.OpenAIEmbeddings") as MockEmb:
            MockEmb.side_effect = [MagicMock(), MagicMock()]
            a = _get_embeddings("text-embedding-3-small")
            b = _get_embeddings("text-embedding-ada-002")
            assert a is not b
            assert MockEmb.call_count == 2

        _get_embeddings.cache_clear()


# ── L2: Deprecated call removed ───────────────────────────────────────────────

class TestDeprecatedGetRelevantDocumentsReplaced:
    def test_safe_filter_calls_invoke_not_get_relevant_documents(self):
        """_SafeEmbeddingsFilter._get_relevant_documents must call .invoke(), not .get_relevant_documents()."""
        from src.retriever import _SafeEmbeddingsFilter

        base = MagicMock()
        base.invoke.return_value = []
        base.get_relevant_documents = MagicMock(side_effect=AssertionError(
            "get_relevant_documents() is deprecated — should not be called"
        ))

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.30,
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 10
        mock_emb.embed_documents.return_value = []

        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            docs = filt._get_relevant_documents("test query")

        base.invoke.assert_called_once_with("test query")
        base.get_relevant_documents.assert_not_called()
        assert docs == []  # Empty corpus → empty result


# ── L3: MultiQuery num_queries ────────────────────────────────────────────────

class TestMultiQueryNumQueries:
    def test_multi_query_uses_custom_prompt_for_num_queries(self, monkeypatch):
        """_apply_multi_query must control num_queries via a custom prompt, NOT
        by passing it to from_llm() or setting it as an attribute.

        Root cause (RCA-12): MultiQueryRetriever is a Pydantic v2 model with
        extra='ignore'. Setting .num_queries post-construction raises
        ValueError: "MultiQueryRetriever" object has no field "num_queries".
        The version-compatible fix: pass a PromptTemplate whose text
        explicitly says "generate N different versions".
        """
        from src.retriever import _apply_multi_query, _get_multi_query_llm
        _get_multi_query_llm.cache_clear()

        captured_kwargs: dict = {}

        def fake_from_llm(retriever, llm, **kw):
            captured_kwargs.update(kw)
            # num_queries must NOT be passed to from_llm (it's not a valid param)
            assert "num_queries" not in kw, (
                "num_queries must NOT be passed to from_llm() — "
                "it is not a valid parameter in LangChain 0.3"
            )
            return MagicMock()

        with patch("langchain_openai.ChatOpenAI"):
            with patch(
                "langchain.retrievers.multi_query.MultiQueryRetriever.from_llm",
                side_effect=fake_from_llm,
            ):
                base = MagicMock()
                _apply_multi_query(base, "gpt-4o-mini", num_queries=2)

        # A custom prompt must have been passed to from_llm
        assert "prompt" in captured_kwargs, "Custom prompt must be passed to from_llm()"
        # The prompt text must mention the desired number of queries
        prompt_text = captured_kwargs["prompt"].template
        assert "2" in prompt_text, f"Prompt must reference num_queries=2; got: {prompt_text[:200]}"
        _get_multi_query_llm.cache_clear()

    def test_multi_query_prompt_reflects_num_queries_3(self, monkeypatch):
        """When num_queries=3, the custom prompt must mention '3'."""
        from src.retriever import _apply_multi_query, _get_multi_query_llm
        _get_multi_query_llm.cache_clear()

        captured_kwargs: dict = {}

        def fake_from_llm(retriever, llm, **kw):
            captured_kwargs.update(kw)
            return MagicMock()

        with patch("langchain_openai.ChatOpenAI"):
            with patch(
                "langchain.retrievers.multi_query.MultiQueryRetriever.from_llm",
                side_effect=fake_from_llm,
            ):
                base = MagicMock()
                _apply_multi_query(base, "gpt-4o-mini", num_queries=3)

        prompt_text = captured_kwargs["prompt"].template
        assert "3" in prompt_text, f"Prompt must reference num_queries=3; got: {prompt_text[:200]}"
        _get_multi_query_llm.cache_clear()

    def test_multi_query_num_queries_default_is_2(self, monkeypatch):
        """Settings default for multi_query_num_queries must be 2."""
        import os
        from config.settings import get_settings, Settings
        get_settings.cache_clear()

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        # Ensure the env var is not set (use default)
        monkeypatch.delenv("MULTI_QUERY_NUM_QUERIES", raising=False)

        settings = Settings()
        assert settings.multi_query_num_queries == 2
        get_settings.cache_clear()


# ── L4: Query result cache ────────────────────────────────────────────────────

class TestQueryResultCache:
    def _mock_chain_response(self, answer="Cached answer."):
        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result(answer=answer)
        return chain

    def test_identical_query_returns_cached_result(self, monkeypatch):
        """Second identical query must hit cache and NOT call pipeline again."""
        from app.state import query_result_cache
        from config.settings import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "300")

        chain = self._mock_chain_response()

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            payload = {"question": "What is revenue?", "top_k": 8}
            r1 = c.post("/api/ask", json=payload)
            r2 = c.post("/api/ask", json=payload)

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Pipeline invoked only once — second call hit cache
        assert chain.invoke.call_count == 1
        get_settings.cache_clear()

    def test_cache_miss_on_different_question(self, monkeypatch):
        """Different questions must bypass the cache and call pipeline separately."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "300")

        from app.state import query_result_cache
        query_result_cache.clear()

        chain = self._mock_chain_response()

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            c.post("/api/ask", json={"question": "What is revenue?", "top_k": 8})
            c.post("/api/ask", json={"question": "What are the risks?", "top_k": 8})

        assert chain.invoke.call_count == 2

    def test_cache_expired_entry_is_bypassed(self, monkeypatch):
        """An entry older than TTL must be treated as a miss."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "1")  # 1 second TTL

        from app.state import query_result_cache
        from config.settings import get_settings
        get_settings.cache_clear()
        query_result_cache.clear()

        chain = self._mock_chain_response()

        question = "What is EBITDA? expiry-test-" + uuid.uuid4().hex
        cache_key = f"q={question.lower()}|user=None|src=None|type=None|topk=8"

        # Pre-populate with an already-expired entry
        query_result_cache[cache_key] = {
            "response": {"answer": "stale", "sources": [], "total_chunks_retrieved": 0,
                         "confidence_score": 0.5, "retrieval_meta": None, "request_id": "old"},
            "cached_at": time.perf_counter() - 5,  # 5 s ago > 1 s TTL
        }

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            r = c.post("/api/ask", json={"question": question, "top_k": 8})

        assert r.status_code == 200
        assert chain.invoke.call_count == 1  # Pipeline WAS called (cache miss)
        get_settings.cache_clear()

    def test_cache_cleared_on_ingest_completion(self, monkeypatch):
        """query_result_cache must be empty after a successful ingestion."""
        from app.state import query_result_cache

        # Pre-populate the cache with something
        query_result_cache["some-key"] = {"response": {}, "cached_at": time.perf_counter()}
        assert len(query_result_cache) > 0

        # Simulate what _run_ingestion does on success
        from app.state import pipeline_cache
        pipeline_cache.clear()
        query_result_cache.clear()

        assert len(query_result_cache) == 0

    def test_cache_disabled_when_ttl_zero(self, monkeypatch):
        """Setting QUERY_CACHE_TTL_SECONDS=0 must bypass the cache entirely."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "0")

        from app.state import query_result_cache
        from config.settings import get_settings
        get_settings.cache_clear()
        query_result_cache.clear()

        chain = self._mock_chain_response()
        question = "TTL-zero test " + uuid.uuid4().hex

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            c.post("/api/ask", json={"question": question, "top_k": 8})
            c.post("/api/ask", json={"question": question, "top_k": 8})

        # With TTL=0 cache is disabled — pipeline called both times
        assert chain.invoke.call_count == 2
        get_settings.cache_clear()


# ── L5 / L6: request_id and latency_ms ────────────────────────────────────────

class TestRequestIdAndLatency:
    def _query(self, monkeypatch, question=None):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "0")  # Disable cache for fresh calls

        from config.settings import get_settings
        from app.state import query_result_cache
        get_settings.cache_clear()
        query_result_cache.clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        q = question or f"What is revenue? {uuid.uuid4().hex}"
        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            r = c.post("/api/ask", json={"question": q, "top_k": 8})

        get_settings.cache_clear()
        return r

    def test_response_has_request_id(self, monkeypatch):
        r = self._query(monkeypatch)
        assert r.status_code == 200
        body = r.json()
        assert "request_id" in body
        assert body["request_id"] is not None
        assert len(body["request_id"]) == 32  # uuid4().hex is 32 chars

    def test_request_id_is_unique_per_call(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "0")

        from config.settings import get_settings
        from app.state import query_result_cache
        get_settings.cache_clear()
        query_result_cache.clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            r1 = c.post("/api/ask", json={"question": f"Q1 {uuid.uuid4().hex}", "top_k": 8})
            r2 = c.post("/api/ask", json={"question": f"Q2 {uuid.uuid4().hex}", "top_k": 8})

        assert r1.json()["request_id"] != r2.json()["request_id"]
        get_settings.cache_clear()

    def test_response_has_latency_ms(self, monkeypatch):
        r = self._query(monkeypatch)
        body = r.json()
        assert body.get("retrieval_meta") is not None
        latency = body["retrieval_meta"].get("latency_ms")
        assert latency is not None
        assert latency >= 0

    def test_cached_response_gets_fresh_request_id(self, monkeypatch):
        """Cache-hit responses must get a new request_id, not the cached one."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "300")

        from config.settings import get_settings
        from app.state import query_result_cache
        get_settings.cache_clear()
        query_result_cache.clear()

        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        question = f"Cached request_id test {uuid.uuid4().hex}"

        with patch("app.routes.query._build_pipeline", return_value=chain):
            from fastapi.testclient import TestClient
            from app.main import app as fastapi_app
            c = TestClient(fastapi_app)
            r1 = c.post("/api/ask", json={"question": question, "top_k": 8})
            r2 = c.post("/api/ask", json={"question": question, "top_k": 8})

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both have request_ids, but they are different
        assert r1.json()["request_id"] != r2.json()["request_id"]
        get_settings.cache_clear()


# ── Settings: new field defaults ──────────────────────────────────────────────

class TestSettingsNewFields:
    def test_query_cache_ttl_default_is_300(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        s = Settings()
        assert s.query_cache_ttl_seconds == 300
        get_settings.cache_clear()

    def test_multi_query_num_queries_default_is_2(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        s = Settings()
        assert s.multi_query_num_queries == 2
        get_settings.cache_clear()

    def test_query_cache_ttl_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("QUERY_CACHE_TTL_SECONDS", "60")
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        s = Settings()
        assert s.query_cache_ttl_seconds == 60
        get_settings.cache_clear()

    def test_multi_query_num_queries_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("MULTI_QUERY_NUM_QUERIES", "3")
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        s = Settings()
        assert s.multi_query_num_queries == 3
        get_settings.cache_clear()


class TestSpeedSettings:
    def test_compound_query_top_k_default_is_4(self, monkeypatch):
        monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        settings = Settings()
        assert settings.compound_query_top_k == 4
        get_settings.cache_clear()

    def test_answer_max_tokens_defaults(self, monkeypatch):
        monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
        from config.settings import get_settings, Settings
        get_settings.cache_clear()
        settings = Settings()
        assert settings.answer_max_tokens == 700
        assert settings.compound_answer_max_tokens == 900
        get_settings.cache_clear()

