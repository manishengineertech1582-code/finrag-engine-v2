"""
Metadata Enrichment
====================
Adds production-grade metadata to every chunk after chunking.

Fields added here:
  chunk_id     — globally unique ID (shortuuid) for traceability and citations
  ingested_at  — ISO 8601 UTC timestamp (enables time-based filtering / audit)
  file_hash    — SHA256 of the source file (enables dedup queries)
  user_id      — multi-tenancy: scope retrieval per tenant

Fields that must already exist (set by each format-specific loader):
  source        — original filename
  page_or_sheet — page_5 / section_2 / sheet_Revenue_rows_1_50
  doc_type      — pdf | docx | excel | csv | txt
"""

import logging
from typing import List, Optional

import arrow
import shortuuid
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def enrich_chunks(
    chunks: List[Document],
    user_id: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> List[Document]:
    """
    Add chunk_id, ingested_at, and optionally file_hash to every chunk.

    Args:
        chunks:    Chunked documents from chunking.py.
        user_id:   Override user_id (if not already set by the loader).
        file_hash: SHA256 of the source file (for deduplication queries).

    Returns:
        Same document list with enriched metadata (mutated in place).
    """
    now_iso = arrow.utcnow().isoformat()

    for chunk in chunks:
        chunk.metadata["chunk_id"] = shortuuid.uuid()
        chunk.metadata["ingested_at"] = now_iso

        # file_hash enables efficient dedup queries on the chunk level
        if file_hash:
            chunk.metadata["file_hash"] = file_hash

        # Only override user_id if not already injected by the loader
        if user_id and not chunk.metadata.get("user_id"):
            chunk.metadata["user_id"] = user_id

        # Ensure required fields always exist (defensive defaults)
        chunk.metadata.setdefault("source", "unknown")
        chunk.metadata.setdefault("page_or_sheet", "unknown")
        chunk.metadata.setdefault("doc_type", "unknown")
        chunk.metadata.setdefault("user_id", None)

    logger.debug("Enriched %d chunks with metadata.", len(chunks))
    return chunks
