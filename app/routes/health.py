"""
Health Endpoint
================
GET /health — returns vectorstore validity and indexed vector count.

Checks the actual FAISS index (not just directory existence):
  - index.faiss and index.pkl must both be present and non-empty
  - Reports ntotal (number of indexed vectors) via faiss.read_index()
  - Used by load balancers, Docker healthchecks, and Kubernetes probes
"""

import logging
import os

from fastapi import APIRouter

from config.settings import get_settings
from models.response import HealthResponse, OcrDependencies
from src.ingestion.pdf_loader import is_poppler_available, is_tesseract_available

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Report system health, vectorstore validity, and indexed vector count.

    vectorstore_loaded=True only when both index.faiss and index.pkl exist
    and the FAISS index reports at least one vector (ntotal > 0).
    """
    settings = get_settings()
    vs_path = settings.vectorstore_path

    index_file = os.path.join(vs_path, "index.faiss")
    pkl_file = os.path.join(vs_path, "index.pkl")

    files_present = (
        os.path.exists(index_file)
        and os.path.exists(pkl_file)
        and os.path.getsize(index_file) > 0
    )

    indexed_vectors = 0
    if files_present:
        try:
            import faiss as _faiss
            idx = _faiss.read_index(index_file)
            indexed_vectors = int(idx.ntotal)
        except Exception as exc:
            logger.warning("Could not read FAISS index for health check: %s", exc)

    vectorstore_loaded = files_present and indexed_vectors > 0

    return HealthResponse(
        status="ok",
        vectorstore_loaded=vectorstore_loaded,
        indexed_vectors=indexed_vectors,
        environment=settings.app_env,
        ocr=OcrDependencies(
            poppler=is_poppler_available(),
            tesseract=is_tesseract_available(),
        ),
    )
