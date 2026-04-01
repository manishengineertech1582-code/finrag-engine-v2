"""
Document Ingestion Endpoint
============================
POST /api/ingest         — Upload document → queue background ingestion → return job_id
GET  /api/jobs/{job_id}  — Poll ingestion job status

Background pipeline (all CPU-bound steps off the event loop via asyncio.to_thread):
  Stream file → size gate → SHA256 dedup → save with UUID prefix →
  load (format-specific) → format-aware chunk → enrich metadata →
  embed + FAISS upsert → register dedup hash → invalidate pipeline cache

Supported formats: .pdf  .docx  .xlsx  .csv  .txt
"""

import asyncio
import hashlib
import logging
import os
import uuid
from typing import Optional

import arrow
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.state import job_registry, pipeline_cache, query_result_cache
from config.settings import get_settings
from models.response import DocumentListResponse, DocumentRecord, IngestJobResponse, JobStatusResponse
from src.embeddings import load_document_registry
from src.chunking import chunk_documents
from src.embeddings import add_to_vector_store, is_duplicate_file, register_file
from src.ingestion.factory import get_doc_type, load_document
from src.metadata import enrich_chunks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Ingestion"])

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}


@router.post(
    "/ingest",
    response_model=IngestJobResponse,
    status_code=202,
    summary="Upload a document for background ingestion",
)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, DOCX, XLSX, CSV, or TXT file"),
    user_id: Optional[str] = Form(None, description="User/tenant ID for multi-tenancy"),
):
    """
    Upload a document and queue it for background ingestion.

    Returns HTTP 202 with a job_id immediately.
    Poll `GET /api/jobs/{job_id}` to check completion status.
    """
    settings = get_settings()

    # ── Validate extension ────────────────────────────────────────────────────
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported format '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    # ── Stream file in chunks, reject early if too large ─────────────────────
    # Reads in 64KB chunks so we can gate on size without buffering everything.
    CHUNK_SIZE = 65536  # 64 KB per read
    raw_chunks: list[bytes] = []
    total_size = 0
    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > settings.max_file_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"File too large. Maximum allowed size is "
                        f"{settings.max_file_size_mb} MB."
                    ),
                )
            raw_chunks.append(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to read uploaded file: %s", filename)
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.") from exc

    content = b"".join(raw_chunks)

    # ── SHA256 deduplication (per-user) ───────────────────────────────────────
    file_hash = hashlib.sha256(content).hexdigest()
    if is_duplicate_file(file_hash, user_id, settings.vectorstore_path):
        return IngestJobResponse(
            job_id="",
            status="skipped",
            message=(
                f"'{filename}' has already been ingested (identical content detected). "
                "Skipping to avoid duplicate chunks."
            ),
        )

    # ── Save with UUID prefix to prevent filename collisions ──────────────────
    # Namespace under user_id when present for clean multi-tenant separation.
    safe_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    if user_id:
        user_upload_dir = os.path.join(settings.upload_dir, user_id)
        os.makedirs(user_upload_dir, exist_ok=True)
        save_path = os.path.join(user_upload_dir, safe_name)
    else:
        os.makedirs(settings.upload_dir, exist_ok=True)
        save_path = os.path.join(settings.upload_dir, safe_name)

    with open(save_path, "wb") as fh:
        fh.write(content)

    logger.info(
        "File saved | name=%s | size=%d bytes | user=%s",
        safe_name, total_size, user_id,
    )

    # ── Register job ──────────────────────────────────────────────────────────
    job_id = uuid.uuid4().hex
    job_registry[job_id] = {
        "status": "pending",
        "created_at": arrow.utcnow().isoformat(),
        "filename": filename,
        "user_id": user_id,
        "file_hash": file_hash,
    }

    # ── Queue background ingestion ────────────────────────────────────────────
    background_tasks.add_task(
        _run_ingestion,
        job_id=job_id,
        file_path=save_path,
        filename=filename,
        file_hash=file_hash,
        user_id=user_id,
        settings=settings,
    )

    return IngestJobResponse(
        job_id=job_id,
        status="pending",
        message=(
            f"'{filename}' queued for ingestion. "
            f"Poll GET /api/jobs/{job_id} for status."
        ),
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List all ingested documents from the persistent registry",
)
async def list_documents(user_id: Optional[str] = None):
    """
    Return all documents that have been successfully ingested.

    Reads from the persistent ingestion registry (vector_store/ingested_files.json).
    This is the authoritative source of truth — it survives server restarts,
    browser refreshes, and process restarts.

    Query params:
        user_id : Optional[str] — filter to one tenant's documents.
    """
    settings = get_settings()
    registry = load_document_registry(settings.vectorstore_path)

    records: list[DocumentRecord] = []
    for key, meta in registry.items():
        # key format: "{user_id}:{file_hash}"
        parts = key.split(":", 1)
        rec_user_id: Optional[str] = parts[0] if len(parts) == 2 else None
        rec_file_hash: Optional[str] = parts[1] if len(parts) == 2 else None

        # Normalise __global__ back to None
        if rec_user_id == "__global__":
            rec_user_id = None

        # Apply user_id filter when requested
        if user_id is not None and rec_user_id != user_id:
            continue

        records.append(DocumentRecord(
            document_id=key,
            filename=meta.get("filename", "unknown"),
            doc_type=meta.get("doc_type", "unknown"),
            chunks_indexed=meta.get("chunks_indexed", 0),
            ingested_at=meta.get("ingested_at", ""),
            user_id=rec_user_id,
            file_hash=rec_file_hash,
        ))

    # Most recently ingested first
    records.sort(key=lambda r: r.ingested_at, reverse=True)

    logger.info("GET /api/documents | user_id=%s | total=%d", user_id, len(records))
    return DocumentListResponse(documents=records, total=len(records))


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll ingestion job status",
)
async def get_job_status(job_id: str):
    """Return the current status of a background ingestion job."""
    job = job_registry.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobStatusResponse(job_id=job_id, **job)


# ── Background worker ─────────────────────────────────────────────────────────

async def _run_ingestion(
    job_id: str,
    file_path: str,
    filename: str,
    file_hash: str,
    user_id: Optional[str],
    settings,
) -> None:
    """
    Execute the full ingestion pipeline in background.

    All CPU-bound and blocking operations run via asyncio.to_thread()
    so they don't block the event loop during concurrent requests.
    """
    job_registry[job_id]["status"] = "processing"
    job_registry[job_id]["started_at"] = arrow.utcnow().isoformat()

    try:
        doc_type = get_doc_type(file_path)

        # ── Load → Chunk → Enrich → Embed (all blocking, off event loop) ──────
        docs = await asyncio.to_thread(load_document, file_path, user_id=user_id)
        if not docs:
            raise ValueError("No extractable content found in the document.")

        chunks = await asyncio.to_thread(chunk_documents, docs, doc_type=doc_type)
        chunks = enrich_chunks(chunks, user_id=user_id, file_hash=file_hash)

        await asyncio.to_thread(
            add_to_vector_store,
            new_chunks=chunks,
            persist_path=settings.vectorstore_path,
            embedding_model=settings.embedding_model,
        )

        # ── Register file hash to prevent future duplicate ingestion ──────────
        register_file(
            file_hash=file_hash,
            user_id=user_id,
            metadata={
                "filename": filename,
                "doc_type": doc_type,
                "chunks_indexed": len(chunks),
                "ingested_at": arrow.utcnow().isoformat(),
            },
            vectorstore_path=settings.vectorstore_path,
        )

        # ── Invalidate pipeline cache + query result cache ────────────────────
        # Both must be cleared so stale pipelines and stale answers are not served
        # after new documents are indexed.
        pipeline_cache.clear()
        query_result_cache.clear()
        logger.info(
            "Pipeline cache and query result cache cleared after ingestion of '%s'.",
            filename,
        )

        job_registry[job_id].update({
            "status": "completed",
            "completed_at": arrow.utcnow().isoformat(),
            "result": {
                "filename": filename,
                "doc_type": doc_type,
                "chunks_indexed": len(chunks),
                "user_id": user_id,
            },
        })
        logger.info(
            "Ingestion complete | job=%s | file=%s | chunks=%d",
            job_id, filename, len(chunks),
        )

    except Exception as exc:
        logger.exception("Ingestion failed | job=%s | file=%s", job_id, filename)
        job_registry[job_id].update({
            "status": "failed",
            "failed_at": arrow.utcnow().isoformat(),
            "error": str(exc),
        })
