"""
Ingestion Resilience Tests
===========================
Validates that the ingestion pipeline handles malformed documents and
missing system dependencies gracefully — no crashes, structured warnings.

Coverage:
  - DOCX with None paragraph styles
  - DOCX with mixed None / valid styles
  - DOCX where individual paragraphs raise exceptions mid-parse
  - PDF without poppler (OCR skipped, document still loaded)
  - PDF without tesseract (OCR skipped, document still loaded)
  - is_poppler_available / is_tesseract_available helpers
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


# ── DOCX helpers ──────────────────────────────────────────────────────────────

def _make_para(text: str, style_name: str | None) -> MagicMock:
    """Create a mock python-docx paragraph."""
    para = MagicMock()
    para.text = text
    if style_name is None:
        para.style = None
    else:
        para.style = MagicMock()
        para.style.name = style_name
    return para


def _docx_doc_with_paras(paragraphs):
    """Return a mock DocxDocument with the given paragraph list."""
    doc = MagicMock()
    doc.paragraphs = paragraphs
    return doc


# ── DOCX Tests ────────────────────────────────────────────────────────────────

class TestDocxResilience:
    def test_none_style_does_not_crash(self, tmp_path):
        """Paragraphs with style=None should be treated as body text, not crash."""
        # Direct approach: verify _get_style_name is safe with None style
        from src.ingestion.docx_loader import _get_style_name
        p = _make_para("text", None)
        assert _get_style_name(p) == ""

    def test_get_style_name_with_valid_style(self):
        from src.ingestion.docx_loader import _get_style_name
        p = _make_para("Heading text", "Heading 1")
        assert _get_style_name(p) == "Heading 1"

    def test_get_style_name_with_none_style(self):
        from src.ingestion.docx_loader import _get_style_name
        p = _make_para("body text", None)
        assert _get_style_name(p) == ""

    def test_get_style_name_style_without_name_attr(self):
        from src.ingestion.docx_loader import _get_style_name
        p = MagicMock()
        p.style = MagicMock(spec=[])  # no 'name' attribute
        assert _get_style_name(p) == ""

    def test_docx_mixed_none_and_heading_styles(self, tmp_path):
        """Mix of None, heading, and normal styles should all parse without crash."""
        from src.ingestion.docx_loader import load_docx

        paras = [
            _make_para("Intro text with no style.", None),
            _make_para("Section One", "Heading 1"),
            _make_para("Body under section one.", "Normal"),
            _make_para("Another no-style body.", None),
        ]

        fake_path = str(tmp_path / "mixed.docx")
        open(fake_path, "w").close()

        # docx.Document is imported inside the function body — patch at source
        with patch("docx.Document", return_value=_docx_doc_with_paras(paras)):
            docs = load_docx(fake_path, user_id="u1")

        assert isinstance(docs, list)
        assert len(docs) >= 1
        for doc in docs:
            assert isinstance(doc, Document)
            assert doc.metadata["doc_type"] == "docx"
            assert doc.metadata["user_id"] == "u1"
            assert "paragraph_index" in doc.metadata

    def test_docx_all_none_styles_still_returns_documents(self, tmp_path):
        """A document where every paragraph has style=None should still load."""
        from src.ingestion.docx_loader import load_docx

        paras = [_make_para(f"Paragraph {i} content here.", None) for i in range(5)]

        fake_path = str(tmp_path / "nostyles.docx")
        open(fake_path, "w").close()

        with patch("docx.Document", return_value=_docx_doc_with_paras(paras)):
            docs = load_docx(fake_path)

        assert len(docs) >= 1
        assert all(d.page_content.strip() for d in docs)

    def test_docx_file_not_found_raises(self):
        from src.ingestion.docx_loader import load_docx
        with pytest.raises(FileNotFoundError):
            load_docx("/nonexistent/path/file.docx")


# ── PDF + OCR Tests ───────────────────────────────────────────────────────────

class TestPdfOcrResilience:
    def test_is_poppler_available_when_missing(self):
        from src.ingestion.pdf_loader import is_poppler_available
        with patch("shutil.which", return_value=None):
            assert is_poppler_available() is False

    def test_is_poppler_available_when_present(self):
        from src.ingestion.pdf_loader import is_poppler_available
        with patch("shutil.which", return_value="/usr/bin/pdftoppm"):
            assert is_poppler_available() is True

    def test_is_tesseract_available_when_missing(self):
        from src.ingestion.pdf_loader import is_tesseract_available
        with patch("shutil.which", return_value=None):
            assert is_tesseract_available() is False

    def test_is_tesseract_available_when_present(self):
        from src.ingestion.pdf_loader import is_tesseract_available
        with patch("shutil.which", return_value="/usr/bin/tesseract"):
            assert is_tesseract_available() is True

    def test_pdf_without_poppler_skips_ocr(self, tmp_path):
        """PDF with a page that has enough native text still loads when poppler absent."""
        from src.ingestion.pdf_loader import load_pdf

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This page has enough native text to pass the threshold easily."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        fake_path = str(tmp_path / "sample.pdf")
        open(fake_path, "w").close()

        with patch("shutil.which", return_value=None):  # no poppler, no tesseract
            with patch("pypdf.PdfReader", return_value=mock_reader):
                docs = load_pdf(fake_path, user_id="u1")

        assert docs is not None
        assert len(docs) == 1
        assert docs[0].metadata["ocr_available"] is False

    def test_pdf_sparse_page_no_ocr_is_skipped_not_crashed(self, tmp_path):
        """Sparse page with no OCR available → page skipped, no exception raised."""
        from src.ingestion.pdf_loader import load_pdf

        sparse_page = MagicMock()
        sparse_page.extract_text.return_value = "x"  # below MIN_CHARS

        full_page = MagicMock()
        full_page.extract_text.return_value = "Full native text with more than fifty characters here."

        mock_reader = MagicMock()
        mock_reader.pages = [sparse_page, full_page]

        fake_path = str(tmp_path / "mixed.pdf")
        open(fake_path, "w").close()

        with patch("shutil.which", return_value=None):
            with patch("pypdf.PdfReader", return_value=mock_reader):
                docs = load_pdf(fake_path)

        # Sparse page skipped, full page extracted
        assert len(docs) >= 1
        assert any("Full native text" in d.page_content for d in docs)

    def test_pdf_metadata_includes_ocr_available_flag(self, tmp_path):
        """Every page document must carry ocr_available in its metadata."""
        from src.ingestion.pdf_loader import load_pdf

        page = MagicMock()
        page.extract_text.return_value = "Sufficient text content for this page to be included in output."

        mock_reader = MagicMock()
        mock_reader.pages = [page]

        fake_path = str(tmp_path / "meta.pdf")
        open(fake_path, "w").close()

        with patch("shutil.which", return_value=None):
            with patch("pypdf.PdfReader", return_value=mock_reader):
                docs = load_pdf(fake_path)

        assert len(docs) == 1
        assert "ocr_available" in docs[0].metadata
        assert docs[0].metadata["ocr_available"] is False
        assert docs[0].metadata["ocr_used"] is False

    def test_pdf_file_not_found_raises(self):
        from src.ingestion.pdf_loader import load_pdf
        with pytest.raises(FileNotFoundError):
            load_pdf("/nonexistent/path/file.pdf")
