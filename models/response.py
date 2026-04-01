"""
Response Schemas
================
All Pydantic v2 models returned by the API.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChunkSource(BaseModel):
    """A single retrieved chunk's provenance."""
    source: str
    page_or_sheet: str
    doc_type: str
    chunk_id: str
    user_id: Optional[str] = None
    snippet: Optional[str] = None


class RetrievalMeta(BaseModel):
    """Metadata about the retrieval process for transparency and debugging."""
    queries_generated: int = 1
    candidates_before_rerank: int = 0
    candidates_after_rerank: int = 0
    hybrid_search: bool = False
    multi_query: bool = False
    latency_ms: Optional[float] = None
    multi_intent_detected: bool = False
    compound_clause_count: int = 1


class QueryResponse(BaseModel):
    """Response from POST /api/ask."""
    answer: str
    sources: List[ChunkSource]
    total_chunks_retrieved: int
    confidence_score: float = 0.0
    retrieval_meta: Optional["RetrievalMeta"] = None
    request_id: Optional[str] = None


class IngestJobResponse(BaseModel):
    """Response from POST /api/ingest."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Response from GET /api/jobs/{job_id}."""
    job_id: str
    status: str
    created_at: str
    filename: Optional[str] = None
    user_id: Optional[str] = None
    file_hash: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    failed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class OcrDependencies(BaseModel):
    """OCR system dependency availability."""
    poppler: bool
    tesseract: bool


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    vectorstore_loaded: bool
    indexed_vectors: int
    environment: str
    ocr: OcrDependencies


class DocumentInfo(BaseModel):
    """Document metadata (used for future list/search endpoints)."""
    filename: str
    doc_type: str
    user_id: Optional[str] = None
    ingested_at: Optional[str] = None


class DocumentRecord(BaseModel):
    """A single document from the persistent ingestion registry."""
    document_id: str
    filename: str
    doc_type: str
    chunks_indexed: int
    ingested_at: str
    user_id: Optional[str] = None
    file_hash: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Response from GET /api/documents."""
    documents: List[DocumentRecord]
    total: int
