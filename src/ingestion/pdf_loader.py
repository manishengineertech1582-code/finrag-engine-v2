"""
PDF Loader — Native + OCR Fallback
=====================================
Strategy:
  1. Try native text extraction via pypdf (fast, accurate for digital PDFs).
  2. If a page has < MIN_CHARS characters AND both poppler + tesseract are
     present, fall back to OCR via pytesseract (handles scanned PDFs).
  3. If OCR dependencies are missing, log once and skip OCR gracefully.

Metadata injected per page:
  source, page, doc_type="pdf", ocr_used, ocr_available, user_id
"""

import logging
import os
import shutil
from typing import List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

MIN_CHARS = 50  # below this threshold, page is likely scanned → use OCR


def is_poppler_available() -> bool:
    """Return True when pdftoppm (poppler) is on PATH."""
    return shutil.which("pdftoppm") is not None


def is_tesseract_available() -> bool:
    """Return True when tesseract is on PATH."""
    return shutil.which("tesseract") is not None


def load_pdf(file_path: str, user_id: str | None = None) -> List[Document]:
    """
    Load a PDF with automatic OCR fallback for scanned pages.

    Args:
        file_path: Absolute or relative path to the PDF file.
        user_id:   Owner / tenant identifier (for multi-tenancy).

    Returns:
        List of LangChain Documents, one per page.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF not found: {file_path}")

    filename = os.path.basename(file_path)
    documents: List[Document] = []

    # Resolve OCR capability once per file — avoid spamming logs per page
    poppler_ok = is_poppler_available()
    tesseract_ok = is_tesseract_available()
    ocr_enabled = poppler_ok and tesseract_ok

    if not ocr_enabled:
        missing = []
        if not poppler_ok:
            missing.append("poppler (pdftoppm)")
        if not tesseract_ok:
            missing.append("tesseract")
        logger.warning(
            "OCR disabled — missing: %s. Scanned pages will be skipped. file=%s",
            ", ".join(missing),
            filename,
        )

    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        logger.info("PDF opened | pages=%d | file=%s", len(reader.pages), filename)

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            ocr_used = False

            if len(text.strip()) < MIN_CHARS:
                if ocr_enabled:
                    logger.info("Page %d sparse — attempting OCR | file=%s", page_num, filename)
                    text, ocr_used = _ocr_page(file_path, page_num)
                else:
                    logger.debug(
                        "Page %d sparse — OCR skipped (dependency missing) | file=%s",
                        page_num,
                        filename,
                    )

            if not text.strip():
                logger.warning(
                    "Page %d empty after extraction%s. Skipping. | file=%s",
                    page_num,
                    " + OCR" if ocr_used else "",
                    filename,
                )
                continue

            documents.append(Document(
                page_content=text,
                metadata={
                    "source": filename,
                    "page": page_num + 1,
                    "page_or_sheet": f"page_{page_num + 1}",
                    "doc_type": "pdf",
                    "ocr_used": ocr_used,
                    "ocr_available": ocr_enabled,
                    "user_id": user_id,
                }
            ))

        logger.info("PDF loaded | pages_extracted=%d | file=%s", len(documents), filename)
        return documents

    except (FileNotFoundError, RuntimeError):
        raise
    except Exception as e:
        logger.exception("Failed to load PDF: %s", file_path)
        raise RuntimeError(f"PDF load failed: {filename}") from e


def _ocr_page(file_path: str, page_num: int) -> tuple[str, bool]:
    """Convert one PDF page to image and extract text via Tesseract OCR."""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(file_path, first_page=page_num + 1, last_page=page_num + 1)
        if not images:
            return "", False

        text = pytesseract.image_to_string(images[0])
        return text, True

    except ImportError:
        logger.warning("OCR Python packages not installed (pdf2image/pytesseract). Skipping OCR.")
        return "", False
    except Exception as e:
        logger.warning("OCR failed for page %d: %s", page_num, e)
        return "", False
