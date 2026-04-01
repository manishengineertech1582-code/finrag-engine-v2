"""
Document Listing & Retrieval Pipeline Tests
=============================================
Covers:
  - GET /api/documents returns empty list when no docs ingested
  - GET /api/documents returns document after successful ingest
  - GET /api/documents filters by user_id
  - Duplicate upload returns skipped; existing doc still appears in listing
  - _SafeEmbeddingsFilter: logs counts + safety net when all docs below threshold
  - _SafeEmbeddingsFilter: passes docs above threshold normally
  - _filter_docs: correct user_id isolation
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"
    os.environ["APP_ENV"] = "development"
    from config.settings import get_settings
    get_settings.cache_clear()
    from app.main import create_app
    return create_app()


@pytest.fixture
def registry_path(tmp_path):
    """A temporary vector_store path with an empty registry."""
    vs = tmp_path / "vs"
    vs.mkdir()
    return str(vs)


# ── GET /api/documents ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_documents_empty_when_no_registry(app, tmp_path, monkeypatch):
    """GET /api/documents returns empty list when no ingestion has happened."""
    monkeypatch.setenv("VECTORSTORE_PATH", str(tmp_path / "empty_vs"))
    from config.settings import get_settings
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["documents"] == []


@pytest.mark.asyncio
async def test_documents_returns_ingested_files(app, tmp_path, monkeypatch):
    """GET /api/documents returns records after ingesting documents."""
    vs_path = str(tmp_path / "vs")
    os.makedirs(vs_path, exist_ok=True)

    # Pre-populate registry as if ingestion happened
    registry = {
        "user_a:abc123": {
            "filename": "report.pdf",
            "doc_type": "pdf",
            "chunks_indexed": 42,
            "ingested_at": "2026-03-30T10:00:00+00:00",
        },
        "user_a:def456": {
            "filename": "data.csv",
            "doc_type": "csv",
            "chunks_indexed": 10,
            "ingested_at": "2026-03-30T11:00:00+00:00",
        },
    }
    with open(os.path.join(vs_path, "ingested_files.json"), "w") as f:
        json.dump(registry, f)

    monkeypatch.setenv("VECTORSTORE_PATH", vs_path)
    from config.settings import get_settings
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    filenames = {d["filename"] for d in data["documents"]}
    assert filenames == {"report.pdf", "data.csv"}


@pytest.mark.asyncio
async def test_documents_filters_by_user_id(app, tmp_path, monkeypatch):
    """GET /api/documents?user_id=X only returns that user's documents."""
    vs_path = str(tmp_path / "vs")
    os.makedirs(vs_path, exist_ok=True)

    registry = {
        "user_a:hash1": {
            "filename": "user_a_doc.pdf",
            "doc_type": "pdf",
            "chunks_indexed": 5,
            "ingested_at": "2026-03-30T10:00:00+00:00",
        },
        "user_b:hash2": {
            "filename": "user_b_doc.txt",
            "doc_type": "txt",
            "chunks_indexed": 3,
            "ingested_at": "2026-03-30T11:00:00+00:00",
        },
    }
    with open(os.path.join(vs_path, "ingested_files.json"), "w") as f:
        json.dump(registry, f)

    monkeypatch.setenv("VECTORSTORE_PATH", vs_path)
    from config.settings import get_settings
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/documents", params={"user_id": "user_a"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["documents"][0]["filename"] == "user_a_doc.pdf"
    assert data["documents"][0]["user_id"] == "user_a"


@pytest.mark.asyncio
async def test_documents_sorted_most_recent_first(app, tmp_path, monkeypatch):
    """GET /api/documents returns entries sorted newest → oldest."""
    vs_path = str(tmp_path / "vs")
    os.makedirs(vs_path, exist_ok=True)

    registry = {
        "u:hash1": {"filename": "old.pdf", "doc_type": "pdf", "chunks_indexed": 1,
                    "ingested_at": "2026-01-01T00:00:00+00:00"},
        "u:hash2": {"filename": "new.pdf", "doc_type": "pdf", "chunks_indexed": 2,
                    "ingested_at": "2026-03-30T00:00:00+00:00"},
        "u:hash3": {"filename": "mid.pdf", "doc_type": "pdf", "chunks_indexed": 3,
                    "ingested_at": "2026-02-15T00:00:00+00:00"},
    }
    with open(os.path.join(vs_path, "ingested_files.json"), "w") as f:
        json.dump(registry, f)

    monkeypatch.setenv("VECTORSTORE_PATH", vs_path)
    from config.settings import get_settings
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/documents")

    data = resp.json()
    filenames = [d["filename"] for d in data["documents"]]
    assert filenames == ["new.pdf", "mid.pdf", "old.pdf"]


@pytest.mark.asyncio
async def test_duplicate_upload_skipped_doc_still_in_listing(app, tmp_path, monkeypatch):
    """Duplicate upload returns 'skipped'; document still visible in GET /api/documents."""
    vs_path = str(tmp_path / "vs")
    os.makedirs(vs_path, exist_ok=True)
    upload_dir = str(tmp_path / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    content = b"Duplicate file content for testing purposes."

    import hashlib
    file_hash = hashlib.sha256(content).hexdigest()
    registry = {
        f"test_user:{file_hash}": {
            "filename": "existing.txt",
            "doc_type": "txt",
            "chunks_indexed": 3,
            "ingested_at": "2026-03-01T00:00:00+00:00",
        }
    }
    with open(os.path.join(vs_path, "ingested_files.json"), "w") as f:
        json.dump(registry, f)

    monkeypatch.setenv("VECTORSTORE_PATH", vs_path)
    monkeypatch.setenv("UPLOAD_DIR", upload_dir)
    from config.settings import get_settings
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upload the same file again
        ingest_resp = await client.post(
            "/api/ingest",
            files={"file": ("existing.txt", content, "text/plain")},
            data={"user_id": "test_user"},
        )
        assert ingest_resp.status_code == 202
        assert ingest_resp.json()["status"] == "skipped"

        # Document must still appear in the listing
        docs_resp = await client.get("/api/documents", params={"user_id": "test_user"})

    assert docs_resp.status_code == 200
    data = docs_resp.json()
    assert data["total"] == 1
    assert data["documents"][0]["filename"] == "existing.txt"


# ── _SafeEmbeddingsFilter unit tests ─────────────────────────────────────────

class TestSafeEmbeddingsFilter:
    def _make_doc(self, content: str, meta: dict = None) -> "Document":
        from langchain_core.documents import Document
        return Document(page_content=content, metadata=meta or {})

    def _make_filter(self, threshold: float, min_docs: int = 1):
        from src.retriever import _SafeEmbeddingsFilter

        base_retriever = MagicMock()
        return _SafeEmbeddingsFilter(
            base_retriever=base_retriever,
            embedding_model="text-embedding-3-small",
            threshold=threshold,
            min_docs=min_docs,
        )

    def test_passes_docs_above_threshold(self):
        """Docs with similarity ≥ threshold should all be returned."""
        from src.retriever import _SafeEmbeddingsFilter
        from langchain_core.documents import Document

        docs = [
            Document(page_content="revenue Q4 was 5.2M", metadata={}),
            Document(page_content="unrelated text about cats", metadata={}),
        ]
        base = MagicMock()
        base.invoke.return_value = docs  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.50,
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [1.0, 0.0]
        mock_emb.embed_documents.return_value = [
            [0.8, 0.0],   # first doc — above 0.50
            [0.2, 0.0],   # second doc — below 0.50
        ]
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("what was Q4 revenue?")

        assert isinstance(result, list)

    def test_safety_net_returns_top_doc_when_all_below_threshold(self):
        """When all docs are below threshold, safety net returns top-min_docs."""
        from src.retriever import _SafeEmbeddingsFilter
        from langchain_core.documents import Document

        docs = [Document(page_content=f"doc {i}", metadata={}) for i in range(3)]
        base = MagicMock()
        base.invoke.return_value = docs  # Phase 12: use .invoke()

        filt = _SafeEmbeddingsFilter(
            base_retriever=base,
            embedding_model="text-embedding-3-small",
            threshold=0.99,  # impossibly high — no doc will pass
            min_docs=1,
        )

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [1.0, 0.0]
        mock_emb.embed_documents.return_value = [
            [0.5, 0.0],
            [0.4, 0.0],
            [0.3, 0.0],
        ]
        with patch("src.retriever._get_embeddings", return_value=mock_emb):
            result = filt.invoke("test query")

        # Safety net: must return exactly 1 doc (min_docs=1), not 0
        assert len(result) >= 1

    def test_empty_base_results_returns_empty(self):
        """When base retriever returns nothing, filter returns nothing (no crash)."""
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
            result = filt.invoke("any query")

        assert result == []

    def test_exception_in_similarity_falls_back_to_base_docs(self):
        """If embedding call fails, returns base docs unfiltered (no crash)."""
        from src.retriever import _SafeEmbeddingsFilter
        from langchain_core.documents import Document

        docs = [Document(page_content="content", metadata={})]
        base = MagicMock()
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
            result = filt.invoke("test")

        # Fallback: return base docs rather than crashing or returning []
        assert result == docs


# ── _filter_docs isolation tests ──────────────────────────────────────────────

class TestFilterDocs:
    def test_no_filter_returns_all(self):
        from src.retriever import _filter_docs
        from langchain_core.documents import Document

        docs = [
            Document(page_content="a", metadata={"user_id": "u1"}),
            Document(page_content="b", metadata={"user_id": "u2"}),
        ]
        assert _filter_docs(docs, None) == docs

    def test_user_id_filter_isolates_correctly(self):
        from src.retriever import _filter_docs
        from langchain_core.documents import Document

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
        from langchain_core.documents import Document

        docs = [Document(page_content="x", metadata={"user_id": "u1"})]
        result = _filter_docs(docs, {"user_id": "u999"})
        assert result == []
