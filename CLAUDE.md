# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FinRAG Engine v2 is a production-grade Retrieval-Augmented Generation (RAG) platform for document-based Q&A. Users upload documents (PDF, DOCX, XLSX, CSV, TXT), which are chunked, embedded, and stored in a FAISS vector index. Questions are answered by retrieving relevant chunks and generating grounded responses with citations via OpenAI models.

## Commands

```bash
# Development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Build/rebuild vector index
python create_index.py                            # indexes data/raw/
python create_index.py --dir path/to/docs         # custom directory
python create_index.py --dir data/ --user-id team_a

# Tests
pytest                              # all tests (32 tests, <3s)
pytest tests/test_api.py            # API endpoint tests
pytest tests/test_ingestion.py      # ingestion pipeline tests
pytest tests/test_api.py::test_health_returns_ok  # single test

# Install packages (use uv, not pip directly)
uv pip install <package> --python .venv/Scripts/python.exe

# Docker
docker-compose up --build
```

## Architecture

**Two main flows — Ingestion and Query:**

### Ingestion (POST /api/ingest → HTTP 202)
File upload → stream + size gate → SHA256 dedup check → save with UUID prefix →
background task via `asyncio.to_thread()` → format-specific loader (`src/ingestion/`) →
format-aware chunk (`src/chunking.py`) → enrich metadata (`src/metadata.py`) →
embed with OpenAI text-embedding-3-small + FileLock write (`src/embeddings.py`) →
store in FAISS (`vector_store/`) → register dedup hash → clear pipeline cache →
poll via `GET /api/jobs/{job_id}`

### Query (POST /api/ask)
Question → prompt injection guard → load cached pipeline (`src/pipeline.py`) →
BM25+FAISS hybrid retrieval + EmbeddingsFilter re-ranking + MultiQueryRetriever
(`src/retriever.py`) → generate answer with citations via gpt-4o-mini + tenacity retry
(`src/generator.py`) → return answer + sources

### Key directories
- `app/` — FastAPI server: `main.py`, `routes/`, `state.py` (shared cache + job registry)
- `src/` — Core RAG pipeline (chunking, embeddings, retrieval, generation)
- `src/ingestion/` — Document loaders: factory pattern routes by extension
- `config/settings.py` — Pydantic BaseSettings with `@lru_cache` singleton; **import via `get_settings()`**
- `models/` — Pydantic request/response schemas
- `static/index.html` — Single-page chat UI
- `data/raw/` — Uploaded documents (namespaced by user_id); `vector_store/` — persisted FAISS index

### Design decisions
- **Async ingestion**: All CPU-bound ops (`load_document`, `chunk_documents`, `add_to_vector_store`) run via `asyncio.to_thread()` in `_run_ingestion()`. Never add synchronous blocking calls directly in async route handlers.
- **FileLock**: `embeddings.py` uses `filelock.FileLock` on `vector_store/.write.lock` for all FAISS writes. Do not write to the index without acquiring this lock.
- **Settings singleton**: `config/settings.py` uses `@lru_cache(maxsize=1)`. Always import via `from config.settings import get_settings` and call `get_settings()`. Never use raw `os.getenv()` in new code.
- **Cache key includes top_k**: `query.py` cache key is `f"topk={top_k}|filters={...}"`. Do not remove top_k or requests with different k values will silently share one pipeline.
- **Dedup registry**: `vector_store/ingested_files.json` maps `"{user_id}:{sha256}"` → metadata. Updated atomically within the FileLock. Checked before saving the file.
- **Hybrid search**: `retriever.py` builds `BM25Retriever` from the FAISS docstore, pre-filtered by `filter_kwargs` for tenant isolation, then ensembles with FAISS/MMR (weights 0.3/0.7). Falls back to FAISS-only if BM25 fails.
- **Re-ranking**: `EmbeddingsFilter` (ContextualCompressionRetriever) drops chunks below `rerank_threshold` (default 0.75). Uses the same OpenAI embeddings — no additional API key needed.
- **MultiQueryRetriever LLM**: Cached via `@lru_cache` in `retriever.py:_get_multi_query_llm()`. Not recreated per pipeline build.
- **Citation accuracy**: DOCUMENT_PROMPT in `generator.py` embeds `[File: X | Location: Y]` into each passage so the LLM cites real metadata, not hallucinated filenames.
- **Format-aware chunking**: `chunking.py` uses different chunk sizes per doc_type: PDF=1200/200, TXT=1000/150, DOCX=800/150, CSV/Excel=1500/0. Inferred from `documents[0].metadata["doc_type"]` if not passed explicitly.
- **Shared state**: `app/state.py` holds `pipeline_cache` and `job_registry`. Both routes import from here. In multi-worker deployments, migrate to Redis.
- **Pipeline cache invalidation**: `ingest.py:_run_ingestion()` calls `pipeline_cache.clear()` after successful ingestion so stale pipelines don't serve old results.
- **Prompt injection guard**: `QueryRequest.question` runs regex against common injection patterns via `@field_validator`. Returns HTTP 422 on match.
- **Health check**: `health.py` uses `faiss.read_index().ntotal` for actual index validity — not directory existence.
- **OCR fallback**: PDF loader auto-detects scanned pages (<50 chars extracted) and falls back to Tesseract OCR. Requires `tesseract` and `poppler-utils` (in Dockerfile; install manually for local dev).
- **Vectorstore must exist before querying**: `load_vector_store()` raises `FileNotFoundError` if the index hasn't been built. Ingest at least one document or run `create_index.py` first.
- **MultiQueryRetriever cost**: ~2–4× LLM calls per query. Disable via `USE_MULTI_QUERY=false` if cost is a concern.

## Environment

Requires `.env` file (see `.env.example`). Key variables:
- `OPENAI_API_KEY` — required
- `OPENAI_MODEL` — default `gpt-4o-mini`
- `EMBEDDING_MODEL` — default `text-embedding-3-small`
- `VECTORSTORE_PATH` — default `vector_store`
- `USE_HYBRID_SEARCH` — default `true` (BM25 + FAISS ensemble)
- `USE_MULTI_QUERY` — default `true`
- `CORS_ORIGINS` — comma-separated origins for production (empty = no cross-origin)

## Tech Stack

Python 3.11+ / FastAPI / LangChain 0.3 / OpenAI / FAISS / rank-bm25 / filelock / tenacity /
pypdf + pytesseract (OCR) / python-docx / openpyxl / pydantic-settings
