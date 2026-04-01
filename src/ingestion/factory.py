"""
Ingestion Factory
==================
Single entry point for loading ANY supported document format.
Routes to the correct format-specific loader based on file extension.

Supported formats:
  .pdf   → PDF loader (native text + Tesseract OCR fallback for scanned pages)
  .docx  → DOCX / Word document loader
  .xlsx  → Excel loader (multi-sheet, row-chunked)
  .csv   → CSV loader (single sheet, row-chunked)
  .txt   → Plain text loader (encoding-aware, paragraph-split)

Usage:
    from src.ingestion.factory import load_document
    docs = load_document("data/report.pdf", user_id="user_123")
"""

import logging
import os
from typing import List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}

_EXT_TO_DOCTYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "excel",
    ".csv": "csv",
    ".txt": "txt",
}


def load_document(file_path: str, user_id: str | None = None) -> List[Document]:
    """
    Detect file format and route to the appropriate loader.

    Args:
        file_path: Absolute or relative path to the document.
        user_id:   Tenant identifier injected into every chunk's metadata.

    Returns:
        List of LangChain Documents with populated metadata.

    Raises:
        ValueError:        If the format is not supported.
        FileNotFoundError: If the file does not exist.
        RuntimeError:      If the loader encounters an unrecoverable error.
    """
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path must be a non-empty string.")

    ext = os.path.splitext(file_path)[1].lower()

    # Check format before existence — gives a clearer error for unsupported types
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported format: '{ext}'. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(
        "Loading document | format=%s | file=%s | user=%s",
        ext, os.path.basename(file_path), user_id,
    )

    if ext == ".pdf":
        from src.ingestion.pdf_loader import load_pdf
        return load_pdf(file_path, user_id=user_id)

    elif ext == ".docx":
        from src.ingestion.docx_loader import load_docx
        return load_docx(file_path, user_id=user_id)

    elif ext == ".xlsx":
        from src.ingestion.excel_loader import load_excel
        return load_excel(file_path, user_id=user_id)

    elif ext == ".csv":
        from src.ingestion.excel_loader import load_csv
        return load_csv(file_path, user_id=user_id)

    elif ext == ".txt":
        from src.ingestion.txt_loader import load_txt
        return load_txt(file_path, user_id=user_id)

    # Defensive: should never reach here given the extension check above
    raise ValueError(f"No loader mapped for extension: {ext}")


def get_doc_type(file_path: str) -> str:
    """Return the canonical doc_type string for a file path."""
    ext = os.path.splitext(file_path)[1].lower()
    return _EXT_TO_DOCTYPE.get(ext, "unknown")
