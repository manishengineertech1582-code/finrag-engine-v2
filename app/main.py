"""
FinRAG Engine — FastAPI Application Entry Point
================================================
Registers all routers, configures CORS and logging, serves the chat UI.

Run (dev):
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Run (prod):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

Endpoints:
    POST /api/ingest        — Upload + background ingestion (PDF/DOCX/Excel/CSV/TXT)
    GET  /api/jobs/{job_id} — Poll ingestion job status
    POST /api/ask           — RAG question answering with citations
    GET  /health            — Health check with indexed vector count
    GET  /docs              — Swagger UI (dev only)
    GET  /                  — Chat UI (static)
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env BEFORE any module reads environment variables
load_dotenv()

from config.settings import get_settings  # noqa: E402 — must be after load_dotenv

settings = get_settings()

# ── LangSmith tracing (set env vars before LangChain imports) ────────────────
if settings.langchain_tracing_v2 and settings.langchain_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FinRAG Engine starting up | env=%s", settings.app_env)
    # Pre-warm required directories
    for d in [settings.upload_dir, "data/processed", settings.vectorstore_path]:
        os.makedirs(d, exist_ok=True)
    yield
    logger.info("FinRAG Engine shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinRAG Engine",
        description=(
            "Production-grade RAG platform for PDF, DOCX, Excel, CSV and TXT documents.\n\n"
            "**Quick start:**\n"
            "1. `POST /api/ingest` — upload a document (returns job_id)\n"
            "2. `GET /api/jobs/{job_id}` — poll until status=completed\n"
            "3. `POST /api/ask` — ask a question\n\n"
            "Supports multi-tenancy via `user_id` and metadata filtering."
        ),
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Development: allow all origins for local testing.
    # Production: only origins in CORS_ORIGINS env var (comma-separated).
    cors_origins = ["*"] if settings.is_development else settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Supabase JWT auth (no-op when jwt_secret not configured) ─────────────
    from app.middleware.auth import SupabaseAuthMiddleware
    app.add_middleware(SupabaseAuthMiddleware, jwt_secret=settings.supabase_jwt_secret)

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.routes.health import router as health_router
    from app.routes.ingest import router as ingest_router
    from app.routes.query import router as query_router

    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(query_router)

    # ── Static UI (must be LAST — catches all unmatched routes) ───────────────
    if os.path.exists("static"):
        app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
