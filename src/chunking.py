"""
Document Chunking — Format-Aware
==================================
Splits loaded Documents into overlapping chunks optimised per document type.

Format-specific defaults (all overridable via kwargs):
  pdf   — 1200 chars / 200 overlap  (larger context for dense financial text)
  txt   — 1000 chars / 150 overlap  (paragraphs already pre-split by loader)
  docx  — 800 chars  / 150 overlap  (section-grouped by loader)
  csv   — 1500 chars / 0   overlap  (row-groups already structured; no overlap needed)
  excel — 1500 chars / 0   overlap  (same as csv)

Strategy: RecursiveCharacterTextSplitter
  Paragraphs → Sentences → Words → Characters
"""

import logging
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Defaults used when doc_type is unknown or unrecognised
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150

# Per-format overrides: (chunk_size, chunk_overlap)
_FORMAT_DEFAULTS: dict[str, tuple[int, int]] = {
    "pdf":   (1200, 200),
    "txt":   (1000, 150),
    "docx":  (800,  150),
    "csv":   (1500, 0),
    "excel": (1500, 0),
}


def chunk_documents(
    documents: List[Document],
    doc_type: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Document]:
    """
    Split documents into overlapping chunks.

    doc_type is inferred from the first document's metadata if not provided.
    Explicit chunk_size / chunk_overlap always take priority over format defaults.

    Args:
        documents:     Input LangChain Documents.
        doc_type:      Format hint: "pdf" | "txt" | "docx" | "csv" | "excel".
        chunk_size:    Override max characters per chunk.
        chunk_overlap: Override overlap characters between adjacent chunks.

    Returns:
        List of chunked Documents (all metadata preserved).
    """
    if not documents:
        raise ValueError("No documents provided for chunking.")

    # Infer doc_type from metadata if not explicitly passed
    if doc_type is None and documents:
        doc_type = documents[0].metadata.get("doc_type")

    # Resolve effective chunk parameters
    default_size, default_overlap = _FORMAT_DEFAULTS.get(
        doc_type or "", (DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP)
    )
    effective_size = chunk_size if chunk_size is not None else default_size
    effective_overlap = chunk_overlap if chunk_overlap is not None else default_overlap

    if effective_overlap >= effective_size:
        raise ValueError(
            f"chunk_overlap ({effective_overlap}) must be less than "
            f"chunk_size ({effective_size})."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=effective_size,
        chunk_overlap=effective_overlap,
    )

    chunks = splitter.split_documents(documents)
    logger.info(
        "Chunking complete | doc_type=%s | size=%d | overlap=%d | "
        "input_docs=%d | output_chunks=%d",
        doc_type, effective_size, effective_overlap,
        len(documents), len(chunks),
    )
    return chunks
