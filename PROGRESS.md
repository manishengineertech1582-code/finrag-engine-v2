# PROGRESS â€” FinRAG Engine v2 Production Hardening + Full-Stack Build

## Status: COMPLETE âœ… (Phase 15 added)

---

## Phase 1 â€” Foundation
- [x] pyproject.toml â€” fixed Python >=3.14 â†’ >=3.11 (C8)
- [x] requirements.txt â€” added filelock, tenacity, rank-bm25
- [x] Packages installed via `uv pip install`
- [x] config/settings.py â€” full Settings with lru_cache singleton; all env vars typed
- [x] app/state.py â€” shared pipeline_cache + job_registry (both routes)

## Phase 2 â€” Ingestion Pipeline
- [x] src/ingestion/txt_loader.py â€” TXT support: encoding fallback chain, paragraph splitting
- [x] src/ingestion/factory.py â€” .txt route added; format check before existence check
- [x] src/chunking.py â€” format-aware chunk sizes (PDF=1200/200, TXT=1000/150, CSV=1500/0)
- [x] src/embeddings.py â€” FileLock on all writes (C2); SHA256 dedup registry
- [x] src/metadata.py â€” file_hash parameter added
- [x] models/response.py â€” IngestJobResponse, JobStatusResponse added
- [x] models/request.py â€” .txt in doc_type_filter; prompt injection guard via field_validator
- [x] app/routes/ingest.py â€” background jobs (asyncio.to_thread); streaming size check (C6);
                              UUID prefix filenames (C4); dedup check; pipeline cache invalidation

## Phase 3 â€” RAG Pipeline
- [x] src/retriever.py â€” hybrid BM25+FAISS EnsembleRetriever; EmbeddingsFilter re-ranking;
                          MultiQueryRetriever with cached LLM singleton; tenant pre-filter for BM25
- [x] src/generator.py â€” tenacity retry on OpenAI 429/5xx; timeout=60s; prompt injection note
- [x] src/pipeline.py â€” all config from settings (no os.getenv); passes hybrid/rerank params

## Phase 4 â€” API & App
- [x] app/main.py â€” wired to settings (no raw os.getenv); CORS from settings; proper lifespan
- [x] app/routes/query.py â€” cache key now includes top_k (C3); imports from app.state
- [x] app/routes/health.py â€” validates actual FAISS ntotal (not directory existence) (H4)

## Phase 5 â€” Tests
- [x] tests/test_api.py â€” 10 meaningful tests (503 on no vectorstore, 415 on bad format,
                           txt accepted, job polling, prompt injection blocked)
- [x] tests/test_ingestion.py â€” 22 tests: TXT loader Ã— 5, CSV Ã— 3, factory Ã— 4,
                                  chunking Ã— 5, metadata Ã— 3, dedup registry Ã— 2

## Phase 6 â€” Backend Extensions (Full-Stack Prep)
- [x] models/response.py â€” confidence_score added to QueryResponse
- [x] app/routes/query.py â€” confidence_score computed from chunks_retrieved / top_k
- [x] config/settings.py â€” LangSmith + Supabase settings added
- [x] app/main.py â€” LangSmith env var activation when LANGCHAIN_TRACING_V2=true
- [x] app/middleware/auth.py â€” Supabase JWT middleware (no-op in dev without secret)
- [x] requirements: PyJWT==2.9.0 added

## Phase 7 â€” React Frontend (Vite + Tailwind v4 + shadcn + React Query + Zustand)
- [x] frontend/ scaffolded â€” Vite 8, React 19, TypeScript, Tailwind v4
- [x] frontend/src/lib/api.ts â€” typed API client (axios); all endpoints covered
- [x] frontend/src/lib/hooks/ â€” useHealth, useIngest, useJobPolling, useQuery
- [x] frontend/src/state/appStore.ts â€” uploads + recentQueries (Zustand + persist)
- [x] frontend/src/state/authStore.ts â€” user + accessToken (Zustand + persist)
- [x] frontend/src/lib/supabase.ts â€” Supabase client (graceful no-op if unconfigured)
- [x] components/ui/ â€” Button, Badge, Input, Card, Progress, Separator, ScrollArea
- [x] components/layout/ â€” Sidebar, Header (live health), AppLayout
- [x] components/ingest/ â€” DropZone (react-dropzone), FileList (polling), JobStatusBadge
- [x] components/query/ â€” QueryInput (options panel), StreamingText (typewriter), AnswerDisplay
- [x] components/results/ â€” SourceCard (expandable), SourceList
- [x] features/auth/AuthPage.tsx â€” Supabase email auth + guest bypass for dev
- [x] features/ingestion/IngestionPage.tsx
- [x] features/rag/QueryPage.tsx â€” full chat interface with empty state + suggested queries
- [x] pages/Dashboard.tsx â€” stats, quick actions, recent uploads, recent queries
- [x] components/ErrorBoundary.tsx â€” class-based, clean error UI
- [x] App.tsx â€” BrowserRouter + QueryClientProvider + auth guards

## Phase 8 â€” Ingestion Resilience Hardening
- [x] src/ingestion/docx_loader.py â€” `_get_style_name()` helper; per-paragraph try/except;
                                       `paragraph_index` in metadata; safe re-raise chain
- [x] src/ingestion/pdf_loader.py â€” `is_poppler_available()` / `is_tesseract_available()`;
                                      OCR disabled check done once per file (no log spam);
                                      `ocr_available` added to page metadata
- [x] models/response.py â€” `OcrDependencies` model; `ocr` field on `HealthResponse`
- [x] app/routes/health.py â€” reports poppler + tesseract availability in GET /health
- [x] tests/test_ingestion_resilience.py â€” 15 new tests (DOCX style safety, PDF OCR deps)

## Phase 9 â€” Retrieval Fix + Persistent Document Listing
- [x] config/settings.py â€” rerank_threshold: 0.75 â†’ 0.30 (was dropping ALL chunks for text-embedding-3-small)
- [x] src/retriever.py â€” _SafeEmbeddingsFilter: logs candidate counts before/after; safety net returns
                          top-min_docs when all candidates below threshold (never returns empty context)
- [x] src/embeddings.py â€” load_document_registry() public function
- [x] models/response.py â€” DocumentRecord + DocumentListResponse added
- [x] app/routes/ingest.py â€” GET /api/documents: persistent document listing backed by ingested_files.json
- [x] frontend/src/lib/api.ts â€” DocumentRecord type + getDocuments() API call
- [x] frontend/src/lib/hooks/useDocuments.ts â€” NEW: React Query hook with 30s stale time
- [x] frontend/src/state/appStore.ts â€” uploads now persisted (was excluded â€” caused wipe on refresh)
- [x] frontend/src/components/ingest/FileList.tsx â€” merges API docs (persistent) + session uploads (live)
- [x] frontend/src/components/layout/Sidebar.tsx â€” fixed pre-existing TS error (supabase?.auth.signOut)
- [x] tests/test_document_listing.py â€” 12 new tests (document listing, filtering, dedup, SafeEmbeddingsFilter)

## Phase 10 â€” Query Pipeline Contract Fix (RCA-4 + RCA-5)
- [x] src/retriever.py â€” `_SafeEmbeddingsFilter` converted to proper `BaseRetriever` subclass
                          (was plain class with `__getattr__`; MultiQueryRetriever's `.invoke()`
                          now correctly routes through `_get_relevant_documents`, not bypassing
                          reranking via `__getattr__` delegation)
- [x] src/retriever.py â€” `SafeQueryWrapper(BaseRetriever)` added as mandatory outermost layer;
                          normalises dict `{"input": str}` â†’ plain `str` at the system boundary;
                          `get_retriever()` always returns `SafeQueryWrapper` so
                          `create_retrieval_chain` handles it correctly
- [x] tests/test_retrieval_pipeline.py â€” 23 new tests:
                          SafeQueryWrapper input normalisation (dict/str/whitespace/empty/invalid),
                          _SafeEmbeddingsFilter BaseRetriever contract, safety net, exception
                          fallback, threshold filtering, get_retriever() output contract

## Phase 11 â€” UI Redesign + Retrieval Transparency
- [x] models/response.py â€” `RetrievalMeta` model added; `snippet` on `ChunkSource`; `retrieval_meta` on `QueryResponse`
- [x] app/routes/query.py â€” `snippet` populated from `doc.page_content[:200]`; `retrieval_meta` computed from settings
- [x] frontend/src/lib/api.ts â€” `snippet`, `RetrievalMeta`, updated `QueryResponse` contract
- [x] frontend/src/state/appStore.ts â€” `retrieval_meta` persisted on `RecentQuery`
- [x] frontend/src/lib/hooks/useQuery.ts â€” forwards `retrieval_meta` to store
- [x] frontend/src/features/rag/QueryPage.tsx â€” improved loading state ("Analyzing documentsâ€¦")
- [x] frontend/src/components/query/AnswerDisplay.tsx â€” retrieval transparency badge + expandable detail
- [x] frontend/src/components/results/SourceCard.tsx â€” snippet preview (collapsed 2-line, expanded full)
- [x] frontend/src/pages/Dashboard.tsx â€” document/chunk counts from persistent `/api/documents`
- [x] tests/test_response_schema.py â€” 8 schema regression tests

## Phase 12 â€” Latency & Architecture Hardening
- [x] config/settings.py â€” `query_cache_ttl_seconds=300`, `multi_query_num_queries=2`
- [x] app/state.py â€” `query_result_cache` dict (cleared on ingest alongside pipeline_cache)
- [x] models/response.py â€” `RetrievalMeta.latency_ms: Optional[float]`; `QueryResponse.request_id: Optional[str]`
- [x] src/retriever.py â€” `_get_embeddings` lru_cache (eliminates OpenAIEmbeddings cold start per query);
                          `.invoke()` replaces deprecated `.get_relevant_documents()`;
                          `num_queries` param threaded to `MultiQueryRetriever` (2 vs LangChain default 3)
- [x] src/pipeline.py â€” passes `multi_query_num_queries` from settings to `get_retriever`
- [x] app/routes/query.py â€” TTL query result cache (hit/miss/expiry); `request_id` per call;
                              `latency_ms` tracking; `queries_generated` from settings
- [x] app/routes/ingest.py â€” `query_result_cache.clear()` on ingest completion
- [x] frontend/src/lib/api.ts â€” `latency_ms`, `request_id` on types; `AbortSignal` on `api.query()`
- [x] frontend/src/state/appStore.ts â€” `request_id`, `latency_ms` on `RecentQuery`
- [x] frontend/src/lib/hooks/useQuery.ts â€” `AbortController` + stale response guard (full rewrite)
- [x] frontend/src/features/rag/QueryPage.tsx â€” staged loading (Retrieving â†’ Reranking â†’ Generating)
- [x] tests/test_latency_hardening.py â€” 18 new tests
- [x] tests/test_retrieval_pipeline.py â€” updated 5 tests for `.invoke()` contract
- [x] tests/test_document_listing.py â€” updated 4 tests for `.invoke()` contract

## Phase 13 â€” Retrieval Fix + UI Redesign (RCA-7, RCA-8, RCA-10)
- [x] src/retriever.py â€” `_apply_multi_query`: removed `num_queries` from `from_llm()`;
                          set `retriever.num_queries = num_queries` post-construction (RCA-7)
                          MultiQueryRetriever now actually runs â€” was silently falling back to base retriever
- [x] tests/test_latency_hardening.py â€” updated L3 test to assert attribute set on retriever,
                          not passed to `from_llm()` (which rejects it in LangChain 0.3)
- [x] tests/test_document_listing.py â€” replaced 4Ã— `filt.get_relevant_documents()` with `filt.invoke()` (RCA-8)
- [x] tests/test_retrieval_pipeline.py â€” replaced 13Ã— `wrapper/filt.get_relevant_documents()` with `.invoke()` (RCA-8)
- [x] frontend/src/components/query/AnswerDisplay.tsx â€” full redesign (RCA-10):
      question as left-accented heading (text-[15px] font-medium, replaces tiny Q-bubble);
      answer text text-[15px] leading-[1.75] (was text-sm);
      sources visible by default (top 3 SourceCards inline, "Show N more" toggle);
      footer always shows: ConfidenceMeter + pipeline tags (Hybrid/MultiQuery/Reranked) + latency clock;
      retrieval detail panel expandable with request_id
- [x] frontend/src/features/rag/QueryPage.tsx â€” layout + UX hardening (RCA-10):
      max-w-3xl â†’ max-w-4xl; `pendingQuestion` state shows question in loading skeleton;
      loading skeleton inside answer-shaped card; space-y-10 between turns; "index empty" warning
      above composer when has prior history; removed unused MessageSquare import

## Phase 14 â€” Adaptive MultiQuery + History Cap + OCR UX (RCA-6, RCA-9, RCA-11)
- [x] app/routes/query.py â€” `_is_complex_query()`: skip MultiQuery for â‰¤4 words / <30 chars queries;
                             `_build_pipeline(use_multi_query)` cache key includes `|mq=` flag;
                             `queries_generated` reflects actual runtime decision not just settings
- [x] frontend/src/state/appStore.ts â€” `HISTORY_LIMIT=5`; `recentQueries.slice(0, 5)` (was 20);
                             `totalQueriesCount` (persisted, never truncated)
- [x] frontend/src/lib/api.ts â€” `OcrDependencies` interface; `HealthResponse.ocr` field added
- [x] frontend/src/features/ingestion/IngestionPage.tsx â€” OCR amber warning banner when
                             Poppler/Tesseract missing; names missing deps explicitly
- [x] frontend/src/pages/Dashboard.tsx â€” "Questions asked" now reads `totalQueriesCount`
- [x] tests/test_adaptive_multiquery_history.py â€” 16 new tests: `_is_complex_query` boundaries,
                             `_build_pipeline` MultiQuery passthrough, cache key differentiation,
                             `queries_generated` in response (simple=1, complex=2, disabled=1)

## Phase 15 â€” MultiQuery Fix + Multi-Intent Detection (RCA-12, RCA-13, RCA-14)
- [x] src/retriever.py â€” `_apply_multi_query`: removed `retriever.num_queries = n` (Pydantic v2
                          `extra='ignore'` raises `ValueError` on unknown attribute assignment);
                          replaced with `PromptTemplate` passed to `from_llm(prompt=...)` that embeds
                          num_queries count in template text â€” version-compatible with LangChain 0.3.x
- [x] models/response.py â€” `RetrievalMeta.multi_intent_detected: bool = False` added
- [x] app/routes/query.py â€” `_is_multi_intent_query()`: True when 2+ `?` or "and also" connectors;
                             `multi_intent_detected` threaded into `RetrievalMeta`
- [x] frontend/src/lib/api.ts â€” `RetrievalMeta.multi_intent_detected?: boolean` added
- [x] frontend/src/components/query/AnswerDisplay.tsx â€” amber warning banner when
                             `meta.multi_intent_detected` is true; suggests splitting compound questions
- [x] tests/test_latency_hardening.py â€” updated L3 tests: assert custom prompt passed to `from_llm()`,
                             prompt text contains num_queries count, `num_queries` NOT passed as kwarg
- [x] tests/test_multiquery_multiintent.py â€” 15 new tests: prompt approach (5), multi-intent
                             heuristic boundaries (8), API response contract (2)

## Test Results
```
140 passed, 0 failed, 3 warnings (backend)
Frontend: tsc -b âœ…  |  npm run build âœ… (633 KB gzip 188 KB)
```

---

## Critical Issues Fixed
| ID | Issue | Fix |
|----|-------|-----|
| C1 | Blocking I/O in async handlers | asyncio.to_thread() in _run_ingestion |
| C2 | FAISS race condition | filelock.FileLock on all write operations |
| C3 | Cache key missing top_k | Cache key = f"topk={top_k}\|filters={...}" |
| C4 | Filename collision | UUID-prefixed filenames under user namespace |
| C6 | File size check after full read | 64KB streaming chunks with early reject |
| C8 | pyproject.toml Python >=3.14 | Fixed to >=3.11 |

## High Priority Fixed
| ID | Issue | Fix |
|----|-------|-----|
| H1 | Dead Settings class | Wired everywhere; all os.getenv() removed |
| H2 | No retry on OpenAI | tenacity: 4 attempts, exponential backoff |
| H4 | Misleading health check | faiss.read_index().ntotal check |
| H5 | No deduplication | SHA256 file registry in vector_store/ingested_files.json |
| H8 | Meaningless test assertion | 503 test now asserts specific status code + detail |

## RAG Upgrades Added
- Hybrid search: BM25Retriever + FAISS/MMR via EnsembleRetriever (weights 0.3/0.7)
- Re-ranking: ContextualCompressionRetriever + EmbeddingsFilter (threshold=0.75)
- MultiQueryRetriever: LLM reused via @lru_cache singleton (no per-call instantiation)
- Format-aware chunking: different chunk sizes per document type
- Prompt injection guard on QueryRequest.question field
- TXT format support (5th document type)
- confidence_score on every query response

## Full-Stack Architecture
```
frontend/                      React 19 + Vite 8 + Tailwind v4
  src/lib/api.ts               Typed axios client; auth header injected automatically
  src/lib/hooks/               useHealth (30s poll) | useIngest (optimistic) | useJobPolling | useQuery
  src/state/                   Zustand: appStore (uploads + history) | authStore (JWT)
  src/components/ui/           Button | Badge | Input | Card | Progress | Separator | ScrollArea
  src/components/layout/       Sidebar | Header (live vector count) | AppLayout
  src/components/ingest/       DropZone | FileList (live job sync) | JobStatusBadge
  src/components/query/        QueryInput | StreamingText (typewriter) | AnswerDisplay
  src/components/results/      SourceCard (expandable) | SourceList
  src/features/                AuthPage | IngestionPage | QueryPage | Dashboard
  vite.config.ts               Proxy /api + /health â†’ localhost:8000 in dev
```

## Phase 16 - Mixed-Intent Query Repair
- [x] RCA completed in the live old-repo query path (pp/routes/query.py, src/retriever.py, src/generator.py).
- [x] Repair plan saved to .agent/plans/8.old-repo-query-repair.md.
- [ ] Implement clause orchestration, semantic normalization, and regression tests for the reported mixed prompt.


- [x] app/routes/query.py - added question normalization, clause splitting, and per-clause query orchestration to stop blended retrieval on mixed prompts.
- [x] tests/test_multiquery_multiintent.py - added regressions for the reported prompt, patient typo normalization, and compound-clause execution.
- [x] Validation - .\\.venv\\Scripts\\pytest.exe tests\\test_multiquery_multiintent.py tests\\test_api.py -q => 21 passed; .\\.venv\\Scripts\\pytest.exe tests\\test_retrieval_pipeline.py tests\\test_latency_hardening.py tests\\test_adaptive_multiquery_history.py -q => 58 passed.


## Phase 17 - Speed and UI Hardening
- [x] Optimization plan saved to .agent/plans/9.speed-and-ui-hardening.md.
- [x] RCA completed for compound-query latency, token overhead, fake streaming delay, and OCR banner relevance in the old repo.
- [ ] Implement backend execution reductions, chat cleanup, and OCR UI fixes.


- [x] config/settings.py, src/pipeline.py, src/generator.py, and app/routes/query.py - reduced compound-query cost via smaller per-clause retrieval and a single final generation pass with token caps.
- [x] models/response.py and frontend/src/lib/api.ts - added compound clause metadata for the chat UI.
- [x] frontend/src/components/query/AnswerDisplay.tsx, frontend/src/components/query/StreamingText.tsx, and frontend/src/features/rag/QueryPage.tsx - cleaned the chat surface and removed artificial post-response lag.
- [x] frontend/src/features/ingestion/IngestionPage.tsx - replaced the unconditional OCR scare banner with a relevant-only, dismissible note for PDF workflows.
- [x] frontend/src/App.tsx - lazy-loaded major routes to split the bundle and improve startup speed.
- [x] Validation - .\\.venv\\Scripts\\pytest.exe tests\\test_multiquery_multiintent.py tests\\test_latency_hardening.py tests\\test_response_schema.py -q => 39 passed; .\\.venv\\Scripts\\pytest.exe tests\\test_api.py tests\\test_adaptive_multiquery_history.py -q => 26 passed; 
npm run build => success with route-split chunks and no oversized bundle warning.


## Phase 18 - Patient Query Repair and Ask Reset
- [x] Repair plan saved to .agent/plans/10.patient-query-and-ask-reset.md.
- [x] RCA completed for under-split patient comparison queries and Ask window state after successful responses.
- [x] Implement backend parsing fixes, composer reset, and regression coverage.


- [x] app/routes/query.py - expanded patient-intent normalization, split coordinated male/female patient comparisons into focused clauses, and disabled MultiQuery for structured patient requests.
- [x] frontend/src/components/query/QueryInput.tsx and frontend/src/features/rag/QueryPage.tsx - clear the Ask composer after successful responses and preserve text on failed queries.
- [x] tests/test_multiquery_multiintent.py - added regressions for patent info for Males, patient comparison splitting, and structured patient-query routing.
- [x] Validation - .\\.venv\\Scripts\\pytest.exe tests\\test_multiquery_multiintent.py tests\\test_api.py -q => 24 passed; 
npm run build => success.


## Phase 19 - Frontend SaaS Redesign
- [x] Redesign plan saved to .agent/plans/11.frontend-saas-redesign.md.
- [x] UX and architecture audit completed across the app shell, Dashboard, Documents, and Query experiences in the old repo.
- [x] Implement the new design system, Perplexity-style answer UI, and token-load visibility.



## Phase 20 - Structured Patient Lookup Repair
- [x] Repair plan saved to .agent/plans/12.female-chennai-patient-structured-lookup.md.
- [x] RCA completed for missing answers on row-style patient queries against tabular uploads.
- [x] Implement deterministic patient-table lookup, structured logging, and regression coverage.



## Phase 21 - Structured Confidence and Clause Budget Repair
- [x] Repair plan saved to .agent/plans/13.structured-patient-confidence-and-clause-budget.md.
- [x] RCA completed from live logs for structured confidence underreporting, clause budget drift, and noisy routing logs.
- [x] Implement confidence overrides, clause-level caps, and hardened observability.
- [x] tests/test_multiquery_multiintent.py - added regressions for structured confidence overrides, clause-level result caps, and compound routing log hygiene.
- [x] Validation - .\.venv\Scripts\pytest.exe tests\test_multiquery_multiintent.py tests\test_api.py -q => 29 passed; .\.venv\Scripts\pytest.exe tests\test_multiquery_multiintent.py tests\test_latency_hardening.py tests\test_response_schema.py -q => 48 passed.

