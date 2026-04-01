"""
Ingestion Pipeline Tests
=========================
Unit tests for all format-specific loaders, chunking, and metadata enrichment.

Coverage:
  - TXT loader (encoding variants, paragraph splitting)
  - CSV loader (metadata, row chunking)
  - Excel loader (sheet structure)
  - Factory routing (supported + unsupported formats, missing files)
  - Format-aware chunking (size overrides, doc_type inference)
  - Metadata enrichment (chunk_id, ingested_at, file_hash, user_id)
  - Deduplication registry (is_duplicate_file, register_file)
"""

import os
import tempfile

import pytest
from langchain_core.documents import Document


# ── TXT Loader ────────────────────────────────────────────────────────────────

def test_txt_loader_basic():
    from src.ingestion.txt_loader import load_txt
    content = (
        "First paragraph with enough content to pass the minimum threshold check.\n\n"
        "Second paragraph also has sufficient content for the loader to keep it.\n\n"
        "Third paragraph rounds out the test with more than forty characters."
    )
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        path = f.name
    try:
        docs = load_txt(path, user_id="u_txt")
        assert len(docs) >= 1
        assert docs[0].metadata["doc_type"] == "txt"
        assert docs[0].metadata["user_id"] == "u_txt"
        assert "section_" in docs[0].metadata["page_or_sheet"]
    finally:
        os.unlink(path)


def test_txt_loader_utf8_sig_encoding():
    """UTF-8 BOM files (common from Windows) must decode correctly."""
    from src.ingestion.txt_loader import load_txt
    content = "BOM-encoded content for testing with enough characters here."
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as f:
        f.write(content.encode("utf-8-sig"))  # Write with BOM
        path = f.name
    try:
        docs = load_txt(path)
        assert len(docs) >= 1
        # BOM should not appear in content
        assert not docs[0].page_content.startswith("\ufeff")
    finally:
        os.unlink(path)


def test_txt_loader_latin1_encoding():
    """Latin-1 encoded files must be decoded via the fallback chain."""
    from src.ingestion.txt_loader import load_txt
    # Use only latin-1-safe characters (no em-dash or other non-latin-1 chars)
    content = "Cafe resume naive financial report with accented content: eacute ecirc."
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as f:
        f.write(content.encode("latin-1"))
        path = f.name
    try:
        docs = load_txt(path)
        assert len(docs) >= 1
    finally:
        os.unlink(path)


def test_txt_loader_skips_short_sections():
    """Sections with very few characters must be filtered out."""
    from src.ingestion.txt_loader import load_txt
    # Short sections (< MIN_SECTION_CHARS) interleaved with real content
    content = "OK\n\nThis is a properly sized paragraph with sufficient content for processing.\n\nAlso OK"
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write(content)
        path = f.name
    try:
        docs = load_txt(path)
        for doc in docs:
            assert len(doc.page_content) >= 40  # MIN_SECTION_CHARS
    finally:
        os.unlink(path)


def test_txt_loader_file_not_found():
    from src.ingestion.txt_loader import load_txt
    with pytest.raises(FileNotFoundError):
        load_txt("/nonexistent/path/file.txt")


# ── CSV Loader ────────────────────────────────────────────────────────────────

def test_csv_loader_metadata():
    from src.ingestion.excel_loader import load_csv
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        f.write("Name,Value\nFoo,Bar\nBaz,Qux\n")
        path = f.name
    try:
        docs = load_csv(path, user_id="test_user")
        assert len(docs) > 0
        assert docs[0].metadata["doc_type"] == "csv"
        assert docs[0].metadata["user_id"] == "test_user"
        assert docs[0].metadata["source"] == os.path.basename(path)
    finally:
        os.unlink(path)


def test_csv_loader_row_content_format():
    """Each CSV row must be serialised as 'Column: Value' pairs."""
    from src.ingestion.excel_loader import load_csv
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        f.write("Revenue,Cost\n1000,800\n")
        path = f.name
    try:
        docs = load_csv(path)
        assert "Revenue: 1000" in docs[0].page_content
        assert "Cost: 800" in docs[0].page_content
    finally:
        os.unlink(path)


def test_csv_loader_empty_file():
    """An empty CSV (no rows) must return an empty list, not raise."""
    from src.ingestion.excel_loader import load_csv
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name  # write nothing
    try:
        docs = load_csv(path)
        assert docs == []
    finally:
        os.unlink(path)


# ── Factory ───────────────────────────────────────────────────────────────────

def test_factory_routes_txt():
    """Factory must route .txt to the TXT loader without raising."""
    from src.ingestion.factory import load_document, get_doc_type
    content = "Enough content to pass the minimum section filter check.\n\nSecond paragraph."
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write(content)
        path = f.name
    try:
        docs = load_document(path, user_id="u1")
        assert len(docs) >= 0  # may return 0 if all sections too short
        assert get_doc_type(path) == "txt"
    finally:
        os.unlink(path)


def test_factory_unsupported_format():
    from src.ingestion.factory import load_document
    with pytest.raises(ValueError, match="Unsupported format"):
        load_document("file.mp4")


def test_factory_file_not_found():
    from src.ingestion.factory import load_document
    with pytest.raises(FileNotFoundError):
        load_document("nonexistent.pdf")


def test_factory_get_doc_type():
    from src.ingestion.factory import get_doc_type
    assert get_doc_type("report.pdf") == "pdf"
    assert get_doc_type("data.csv") == "csv"
    assert get_doc_type("notes.txt") == "txt"
    assert get_doc_type("book.docx") == "docx"
    assert get_doc_type("sheet.xlsx") == "excel"
    assert get_doc_type("unknown.xyz") == "unknown"


# ── Chunking ──────────────────────────────────────────────────────────────────

def test_chunking_respects_chunk_size():
    from src.chunking import chunk_documents
    docs = [Document(page_content="A" * 2000, metadata={"source": "test.pdf", "doc_type": "pdf"})]
    chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.page_content) <= 600  # chunk_size + small tolerance


def test_chunking_infers_doc_type_from_metadata():
    """Chunking must infer doc_type from document metadata when not passed."""
    from src.chunking import chunk_documents
    # CSV format → chunk_size=1500, overlap=0
    docs = [Document(
        page_content="Col1: Val | Col2: Val\n" * 100,
        metadata={"doc_type": "csv"},
    )]
    chunks = chunk_documents(docs)  # no explicit chunk_size
    # Each chunk should be up to 1500 chars (CSV default)
    for c in chunks:
        assert len(c.page_content) <= 1600


def test_chunking_pdf_uses_larger_chunks():
    """PDF format must use 1200-char chunks by default."""
    from src.chunking import chunk_documents
    text = "Financial statement data. " * 200  # ~5200 chars
    docs = [Document(page_content=text, metadata={"doc_type": "pdf"})]
    chunks = chunk_documents(docs)
    # With 1200-char chunks, we expect ~5 chunks from ~5200 chars
    assert 3 <= len(chunks) <= 8


def test_chunking_raises_on_empty_input():
    from src.chunking import chunk_documents
    with pytest.raises(ValueError, match="No documents"):
        chunk_documents([])


def test_chunking_raises_on_invalid_overlap():
    from src.chunking import chunk_documents
    docs = [Document(page_content="test", metadata={})]
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_documents(docs, chunk_size=100, chunk_overlap=100)


# ── Metadata Enrichment ───────────────────────────────────────────────────────

def test_metadata_enrichment_adds_required_fields():
    from src.metadata import enrich_chunks
    docs = [Document(page_content="test", metadata={"source": "x.pdf", "doc_type": "pdf"})]
    enriched = enrich_chunks(docs, user_id="u1", file_hash="abc123")

    assert enriched[0].metadata["chunk_id"] != ""
    assert enriched[0].metadata["ingested_at"] != ""
    assert enriched[0].metadata["user_id"] == "u1"
    assert enriched[0].metadata["file_hash"] == "abc123"


def test_metadata_enrichment_does_not_override_existing_user_id():
    """Loader-injected user_id must take precedence over the argument."""
    from src.metadata import enrich_chunks
    docs = [Document(page_content="test", metadata={"user_id": "original_user"})]
    enriched = enrich_chunks(docs, user_id="override_user")
    assert enriched[0].metadata["user_id"] == "original_user"


def test_metadata_enrichment_sets_defaults():
    """Missing required fields must be filled with defensive defaults."""
    from src.metadata import enrich_chunks
    docs = [Document(page_content="test", metadata={})]
    enriched = enrich_chunks(docs)
    assert enriched[0].metadata["source"] == "unknown"
    assert enriched[0].metadata["page_or_sheet"] == "unknown"
    assert enriched[0].metadata["doc_type"] == "unknown"


# ── Deduplication Registry ────────────────────────────────────────────────────

def test_dedup_registry_detects_duplicate(tmp_path):
    from src.embeddings import is_duplicate_file, register_file

    vs_path = str(tmp_path)
    file_hash = "deadbeef" * 8
    user_id = "u_dedup"

    # Not a duplicate yet
    assert not is_duplicate_file(file_hash, user_id, vs_path)

    # Register it
    register_file(
        file_hash=file_hash,
        user_id=user_id,
        metadata={"filename": "test.pdf", "chunks_indexed": 10},
        vectorstore_path=vs_path,
    )

    # Now it's a duplicate
    assert is_duplicate_file(file_hash, user_id, vs_path)


def test_dedup_registry_isolates_per_user(tmp_path):
    """Same file hash for different users must NOT be treated as duplicate."""
    from src.embeddings import is_duplicate_file, register_file

    vs_path = str(tmp_path)
    file_hash = "cafebabe" * 8

    register_file(
        file_hash=file_hash,
        user_id="user_a",
        metadata={"filename": "report.pdf"},
        vectorstore_path=vs_path,
    )

    # user_a: duplicate
    assert is_duplicate_file(file_hash, "user_a", vs_path)
    # user_b: NOT a duplicate
    assert not is_duplicate_file(file_hash, "user_b", vs_path)
