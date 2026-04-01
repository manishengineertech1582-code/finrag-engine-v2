# FinRAG Engine v2

FinRAG Engine v2 is a document-grounded question answering platform for teams that need fast, explainable answers from uploaded business files. It combines a FastAPI backend, a FAISS-based hybrid retrieval pipeline, and a React frontend for ingestion, monitoring, and query workflows.

The repository is suitable for:

- product demos that need visible source citations
- internal knowledge assistants over PDFs, Word docs, spreadsheets, and text
- multi-tenant document workspaces scoped by `user_id`
- structured CSV/XLSX lookups where exact row retrieval matters

## Why this project matters

Most chat interfaces fail in demos because they answer confidently without showing evidence. FinRAG is built around the opposite behavior:

- answers are expected to stay grounded in uploaded documents
- every factual answer is backed by citations
- ingestion is immediate, so new uploads can be queried without retraining
- the UI exposes confidence, latency, and source chunks instead of hiding retrieval
- structured patient-style table queries can bypass semantic retrieval and use deterministic row matching

This makes the project useful both as an engineering foundation and as a demo artifact that explains itself clearly to customers, operators, and investors.

## What the platform does

### Core capabilities

- Ingests `PDF`, `DOCX`, `XLSX`, `CSV`, and `TXT` files.
- Stores embeddings in a local FAISS index under `vector_store/`.
- Uses hybrid retrieval: BM25 keyword search plus FAISS semantic search.
- Re-ranks retrieved chunks with an embedding similarity filter.
- Expands harder questions with MultiQuery retrieval when enabled.
- Splits compound questions into focused clauses before answering.
- Supports metadata filtering by `user_id`, `doc_type`, and `source`.
- Rejects obvious prompt-injection patterns at request validation time.
- Tracks ingestion jobs asynchronously and exposes job polling endpoints.
- Ships with a React frontend for authentication, document upload, dashboarding, and question answering.

### Demo-ready behaviors

- Upload progress and ingestion status are visible in the UI.
- The dashboard shows document count, chunk count, vector count, recent queries, and latency posture.
- The query workspace shows staged loading, confidence, retrieval metadata, and expandable source cards.
- OCR dependency status is surfaced through `GET /health` and reflected in the frontend.

## Product architecture

```text
User uploads file or asks question
        |
        v
React frontend
  - Auth page
  - Dashboard
  - Ingestion page
  - Query workspace
        |
        v
FastAPI backend
  - POST /api/ingest
  - GET  /api/jobs/{job_id}
  - GET  /api/documents
  - POST /api/ask
  - GET  /health
        |
        +--> Ingestion pipeline
        |     load -> chunk -> enrich metadata -> embed -> persist to FAISS
        |
        +--> Retrieval pipeline
              FAISS/MMR + BM25 -> rerank -> optional MultiQuery -> grounded generation
        |
        v
Storage
  - data/raw/          uploaded files
  - vector_store/      FAISS index + dedup registry + write lock
  - static/            optional built frontend served by FastAPI
```

## Retrieval and answer flow

1. A document is uploaded through `POST /api/ingest`.
2. The backend validates extension and size, computes SHA256, checks dedup state, and saves the file under `data/raw/`.
3. The background ingestion task loads the file with a format-specific loader.
4. The file is chunked with format-aware defaults.
5. Metadata is attached to each chunk:
   - `source`
   - `page_or_sheet`
   - `doc_type`
   - `chunk_id`
   - `ingested_at`
   - `file_hash`
   - `user_id`
6. Chunks are embedded with OpenAI embeddings and written to FAISS with a filesystem lock.
7. A query sent to `POST /api/ask` is normalized, optionally decomposed into focused clauses, and checked for structured patient-table routing.
8. The retriever combines keyword and vector search, re-ranks candidates, and optionally generates alternate phrasings.
9. The generator answers using only the provided context and returns sources, confidence, retrieval metadata, and request ID.

## Supported document types

| Format | Extension | Loader behavior |
| --- | --- | --- |
| PDF | `.pdf` | Native text extraction with OCR fallback for low-text pages when Poppler and Tesseract are available |
| Word | `.docx` | Section-aware extraction with resilient paragraph handling |
| Excel | `.xlsx` | Multi-sheet loading with row-oriented serialization |
| CSV | `.csv` | Row-based serialization for retrieval and structured lookup |
| Plain text | `.txt` | Text file loading with chunking for paragraph-style content |

## Repository map

This is the important source layout. Generated directories such as `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `vector_store/`, and `__pycache__/` are runtime artifacts and are not the core implementation.

```text
finrag-engine-old/
|-- app/                    FastAPI app entrypoint, routes, middleware, and services
|-- config/                 Environment-backed application settings
|-- data/                   Uploaded and processed document storage
|-- frontend/               React SPA used for demos and day-to-day interaction
|-- models/                 Pydantic request and response schemas
|-- src/                    Core ingestion, retrieval, metadata, and generation logic
|-- static/                 Optional built frontend served by FastAPI
|-- tests/                  Pytest suite for API, ingestion, retrieval, and regressions
|-- vector_store/           Persisted FAISS index, dedup registry, and file lock
|-- create_index.py         CLI bootstrap script for indexing a local document directory
|-- Dockerfile              Backend container image definition
|-- docker-compose.yml      Local container orchestration for the backend
|-- requirements.txt        Python dependencies
|-- pyproject.toml          Project metadata
|-- README.md               Repository overview and technical guide
```

### Backend application layer

```text
app/
|-- main.py                 FastAPI app factory, CORS, middleware, router wiring, static mount
|-- state.py                In-memory caches and ingestion job registry
|-- middleware/
|   `-- auth.py             Supabase JWT middleware; no-op when secret is absent
|-- routes/
|   |-- health.py           Health check with vector count and OCR dependency reporting
|   |-- ingest.py           Upload endpoint, job polling, document listing
|   `-- query.py            Query normalization, caching, retrieval orchestration
`-- services/
    `-- patient_lookup.py   Deterministic CSV/XLSX row lookup for patient-style questions
```

### Retrieval and ingestion core

```text
src/
|-- chunking.py             Format-aware chunk sizing and splitting
|-- embeddings.py           OpenAI embeddings, FAISS persistence, dedup registry
|-- generator.py            Grounded QA chain and compound-answer generation
|-- metadata.py             Metadata enrichment for every chunk
|-- pipeline.py             Pipeline assembly for full QA or retriever-only flows
|-- retriever.py            Hybrid retrieval, reranking, MultiQuery, safety wrappers
`-- ingestion/
    |-- base.py             Shared ingestion helpers
    |-- factory.py          Loader dispatch by file extension
    |-- pdf_loader.py       PDF extraction and OCR dependency checks
    |-- docx_loader.py      DOCX extraction
    |-- excel_loader.py     Excel and CSV loading
    `-- txt_loader.py       TXT loading
```

### Schemas and configuration

```text
config/
`-- settings.py             Pydantic settings model and singleton loader

models/
|-- request.py              Query request validation and prompt-injection guard
`-- response.py             API response types for health, jobs, documents, and answers
```

### Frontend application

```text
frontend/
|-- src/
|   |-- App.tsx             Router, lazy routes, auth guard, React Query setup
|   |-- main.tsx            Frontend entrypoint
|   |-- assets/             Local frontend assets
|   |-- components/
|   |   |-- ingest/         Upload UX, file list, job status badges
|   |   |-- layout/         Sidebar, header, shared layout shell
|   |   |-- query/          Query input, answer display, streaming text
|   |   |-- results/        Source cards and source list
|   |   `-- ui/             Shared UI primitives
|   |-- features/
|   |   |-- auth/           Supabase auth page plus guest flow
|   |   |-- ingestion/      Document upload page
|   |   `-- rag/            Query workspace
|   |-- lib/
|   |   |-- api.ts          Typed API client
|   |   |-- supabase.ts     Optional Supabase client bootstrap
|   |   `-- hooks/          Query, health, ingest, document, and polling hooks
|   |-- pages/
|   |   `-- Dashboard.tsx   Overview metrics and recent activity
|   `-- state/
|       |-- appStore.ts     Upload history, recent queries, local stats
|       `-- authStore.ts    Persisted user and token state
|-- package.json            Frontend scripts and dependencies
`-- vite.config.ts          Dev server and API proxy configuration
```

### Testing layout

```text
tests/
|-- test_api.py                         API contract coverage
|-- test_ingestion.py                   Loader, chunking, metadata, dedup coverage
|-- test_ingestion_resilience.py        OCR and malformed document handling
|-- test_document_listing.py            Persistent registry and listing behavior
|-- test_retrieval_pipeline.py          SafeQueryWrapper and reranker behavior
|-- test_latency_hardening.py           Cache, latency, and request-id regression checks
|-- test_adaptive_multiquery_history.py MultiQuery heuristics and cache behavior
|-- test_multiquery_multiintent.py      Compound-query and structured-lookup behavior
`-- test_response_schema.py             Response contract regression coverage
```

## Key technical decisions

### Hybrid retrieval

The retrieval stack combines:

- BM25 keyword retrieval for exact terms, identifiers, and entity matches
- FAISS semantic retrieval using MMR for relevance plus diversity
- an embedding-based reranker to trim low-value candidates

This is a better fit for mixed business corpora than vector-only retrieval because users often ask both semantic and exact-match questions.

### Deterministic structured lookup

When a question looks like a patient-table request, the backend can bypass vector retrieval and scan uploaded CSV/XLSX rows directly. This is important because tabular lookups often need exact row filtering rather than approximate semantic matching.

### Multi-tenancy

Documents and queries can be scoped by `user_id`. Filtering is applied both at retrieval time and in document listing, so multiple user workspaces can coexist on the same service instance.

### File-based persistence

The current implementation persists:

- uploaded files in `data/raw/`
- FAISS artifacts in `vector_store/`
- dedup registry in `vector_store/ingested_files.json`
- write coordination in `vector_store/.write.lock`

This keeps the stack easy to run locally and easy to demo without adding external infrastructure.

## Quick start

### 1. Backend setup

Use Python 3.12 for local development.

```bash
python -m venv .venv
# PowerShell
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set at least:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

Start the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

- API: `http://127.0.0.1:8000`
- docs: `http://127.0.0.1:8000/docs` in development only
- health: `http://127.0.0.1:8000/health`

### 2. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL:

- app: `http://127.0.0.1:5173`

The Vite dev server proxies `/api` and `/health` to the backend on port `8000`.

### Frontend authentication behavior

- If `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are configured, the app uses Supabase auth.
- If those variables are not configured, the UI exposes a guest mode for demos and local development.

### 3. Upload and query

1. Open the frontend.
2. Sign in or continue as guest.
3. Upload one or more supported documents from the Documents page.
4. Wait for ingestion to complete.
5. Go to the Query Workspace and ask a grounded question.
6. Inspect citations, confidence, latency, and supporting chunks.

## Running with Docker

The root `docker-compose.yml` starts the backend service and mounts local data directories:

```bash
docker compose up --build
```

Mounted volumes:

- `./data -> /app/data`
- `./vector_store -> /app/vector_store`
- `./static -> /app/static`

Important notes:

- The compose file runs the backend only.
- FastAPI serves `static/` if the directory exists, but this repository does not automatically build and copy the React app into `static/`.
- For a production-style single-container demo, build the frontend and copy `frontend/dist/*` into `static/`.

Frontend production build:

```bash
cd frontend
npm run build
```

## CLI indexing

You can bootstrap the vector store from a local document directory without using the upload API:

```bash
python create_index.py --dir data/raw
python create_index.py --dir data/raw --user-id demo_user
```

`create_index.py` currently supports indexing `PDF`, `DOCX`, `XLSX`, `CSV`, and `TXT` files from a directory.

## Configuration reference

### Backend environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required OpenAI API key | none |
| `OPENAI_MODEL` | Chat model used for answer generation | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | Embedding model used for indexing and reranking | `text-embedding-3-small` |
| `VECTORSTORE_PATH` | FAISS persistence directory | `vector_store` |
| `UPLOAD_DIR` | Uploaded file storage root | `data/raw` |
| `MAX_FILE_SIZE_MB` | Maximum accepted upload size | `50` |
| `TOP_K` | Default retrieval depth | `8` |
| `USE_MULTI_QUERY` | Enable MultiQuery expansion | `true` |
| `USE_HYBRID_SEARCH` | Enable BM25 plus FAISS retrieval | `true` |
| `HYBRID_BM25_WEIGHT` | BM25 weight inside the ensemble retriever | `0.3` |
| `RERANK_THRESHOLD` | Embedding similarity cutoff for reranking | `0.30` |
| `QUERY_CACHE_TTL_SECONDS` | Query response cache TTL | `300` |
| `MULTI_QUERY_NUM_QUERIES` | Alternate phrasings generated for complex queries | `2` |
| `COMPOUND_QUERY_TOP_K` | Retrieval depth per clause for split queries | `4` |
| `ANSWER_MAX_TOKENS` | Max tokens for single-question answers | `700` |
| `COMPOUND_ANSWER_MAX_TOKENS` | Max tokens for compound answers | `900` |
| `APP_ENV` | `development` or `production` | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CORS_ORIGINS` | Comma-separated production origins | empty |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing | `false` |
| `LANGCHAIN_API_KEY` | LangSmith API key | empty |
| `LANGCHAIN_PROJECT` | LangSmith project name | `finrag-engine` |
| `SUPABASE_URL` | Supabase project URL | empty |
| `SUPABASE_ANON_KEY` | Supabase public key | empty |
| `SUPABASE_JWT_SECRET` | Backend JWT verification secret | empty |

### Frontend environment variables

| Variable | Purpose |
| --- | --- |
| `VITE_SUPABASE_URL` | Optional Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Optional Supabase public key |

## API overview

### `POST /api/ingest`

Uploads a document and returns a background job immediately.

- Content type: `multipart/form-data`
- Fields:
  - `file`
  - `user_id` optional

Example response:

```json
{
  "job_id": "8f9f4f8a6f0d4d90aa59f5e5f3f1db9c",
  "status": "pending",
  "message": "'report.pdf' queued for ingestion. Poll GET /api/jobs/8f9f4f8a6f0d4d90aa59f5e5f3f1db9c for status."
}
```

If the same file content has already been ingested for the same user scope, the endpoint returns `status: "skipped"`.

### `GET /api/jobs/{job_id}`

Returns ingestion state for a background job.

Possible statuses:

- `pending`
- `processing`
- `completed`
- `failed`

### `GET /api/documents`

Lists successfully ingested documents from the persistent dedup registry.

Optional query parameter:

- `user_id`

### `POST /api/ask`

Answers a question using the RAG pipeline.

Example request:

```json
{
  "question": "What are the key risks in the uploaded report?",
  "user_id": "demo_user",
  "doc_type_filter": "pdf",
  "top_k": 8
}
```

Available filters:

- `user_id`
- `source_filter`
- `doc_type_filter`
- `top_k`

The current frontend exposes `top_k` and `doc_type_filter` directly in the query UI. `source_filter` is available at the API layer.

Example response shape:

```json
{
  "answer": "The report highlights market volatility [source: report.pdf, page_4].",
  "sources": [
    {
      "source": "report.pdf",
      "page_or_sheet": "page_4",
      "doc_type": "pdf",
      "chunk_id": "abc123",
      "user_id": "demo_user",
      "snippet": "Market volatility remains the primary concern..."
    }
  ],
  "total_chunks_retrieved": 1,
  "confidence_score": 0.95,
  "retrieval_meta": {
    "queries_generated": 1,
    "candidates_before_rerank": 12,
    "candidates_after_rerank": 1,
    "hybrid_search": true,
    "multi_query": false,
    "latency_ms": 284.6,
    "multi_intent_detected": false,
    "compound_clause_count": 1
  },
  "request_id": "9b84b6396f2c44bd9b0a22d032642f44"
}
```

### `GET /health`

Returns service health plus OCR dependency visibility.

Example response:

```json
{
  "status": "ok",
  "vectorstore_loaded": true,
  "indexed_vectors": 1847,
  "environment": "development",
  "ocr": {
    "poppler": true,
    "tesseract": true
  }
}
```

## Frontend experience

### Main routes

| Route | Purpose |
| --- | --- |
| `/auth` | Supabase sign-in/sign-up or guest mode |
| `/` | Dashboard with readiness, document stats, recent answers, and latency posture |
| `/ingest` | Upload flow, OCR readiness, file list, and job timeline |
| `/query` | Query workspace with suggested prompts, staged loading, answers, and source inspection |

### What users can do in the UI

- upload files with drag and drop
- monitor job status live
- browse ingested documents
- ask natural-language questions
- tune retrieval depth through `top_k`
- filter by document type in the query input
- inspect source cards with snippets, chunk IDs, and locations
- review retrieval metadata, request IDs, and confidence estimates

## Testing and quality

Backend coverage is implemented with `pytest`. The test suite focuses on retrieval behavior, ingestion safety, schema regressions, and API contracts.

Run all tests:

```bash
pytest
```

Run selected suites:

```bash
pytest tests/test_api.py
pytest tests/test_ingestion.py
pytest tests/test_retrieval_pipeline.py
```

Coverage themes in the current suite:

- upload validation and job polling
- loader behavior and ingestion resilience
- dedup and document listing
- retrieval wrapper and reranker behavior
- query caching and latency metadata
- MultiQuery and multi-intent routing
- response schema stability

There are currently no frontend automated tests in this repository. Frontend quality is mainly enforced through the typed API contract, build tooling, and manual workflow validation.

## Demo script

For a clean walkthrough:

1. Start backend and frontend locally.
2. Enter as guest if Supabase is not configured.
3. Upload a PDF and a spreadsheet.
4. Show the Dashboard vector count and document list update.
5. Ask a normal semantic question to demonstrate hybrid retrieval and citations.
6. Ask a compound question to demonstrate focused clause handling.
7. Ask a structured patient-style question over CSV/XLSX data to demonstrate deterministic lookup.
8. Expand source cards and retrieval details to show evidence, confidence, and latency.

Suggested demo prompts:

- `Summarize the most important facts in my uploaded documents`
- `List the highest-risk items and show the evidence for each one`
- `What changed across the uploaded files?`
- `List female patients from Chennai`

## Current limitations

This codebase is strong for local use, demos, and single-node deployments, but there are still important scaling limits:

- `pipeline_cache`, `query_result_cache`, and `job_registry` are in-memory and not shared across multiple backend workers.
- FAISS is stored on local disk and is not horizontally distributed.
- OCR requires Poppler and Tesseract on the host machine or in the container.
- Query result caching is per-process and resets on restart.
- The backend has a mature automated test suite, but the frontend does not yet have dedicated automated tests.
- Static frontend serving is optional and currently depends on manually copying built assets into `static/`.

## Recommended next production steps

- Replace in-memory caches and job state with Redis.
- Move background ingestion to a dedicated queue if throughput grows.
- Add a managed vector store if multi-node scale is required.
- Add frontend integration or end-to-end tests.
- Add a repository license file before wider public distribution.

## Tech stack

### Backend

- FastAPI
- Uvicorn
- Pydantic and pydantic-settings
- LangChain
- OpenAI API
- FAISS
- BM25 via `rank-bm25`
- `pypdf`, `python-docx`, `openpyxl`, `pdf2image`, `pytesseract`
- `filelock`, `tenacity`, `arrow`, `shortuuid`

### Frontend

- React
- Vite
- TypeScript
- Zustand
- TanStack Query
- Axios
- Tailwind CSS
- Radix UI primitives
- Supabase client
- Framer Motion

## Repository status notes

- Primary backend entrypoint: `app.main:app`
- `main.py` in the repository root is not the FastAPI server entrypoint
- `vector_store/` and `data/raw/` contain runtime state, not source code
- `frontend/dist/` and `static/` are deployment artifacts, not the authoritative frontend source

FinRAG Engine v2 is best understood as a grounded-document platform with a clear path from local demo to hardened deployment. The codebase already exposes the right product signals for serious evaluation: ingestion transparency, retrieval explainability, exact evidence surfacing, and a visible UI workflow from upload to answer.
