"""
Application State
==================
Shared in-memory state across route handlers within a single process.

In production with multiple uvicorn workers, replace both dicts with Redis:
  - pipeline_cache      → Redis hash (keyed by filter combo)
  - query_result_cache  → Redis hash with TTL
  - job_registry        → Redis hash with TTL (e.g. 24h)

These are intentionally module-level dicts (not class attributes) so that
importing this module from any route always references the same object.
"""

from typing import Any

# Pipeline cache: keyed by (filters + top_k) string hash.
# Cleared on every successful ingestion so queries always see fresh index.
pipeline_cache: dict[str, Any] = {}

# Query result cache: keyed by normalised (question + filter combo) string.
# Each value: {"response": QueryResponse.model_dump(), "cached_at": float (perf_counter)}.
# TTL enforced at read time in app/routes/query.py (settings.query_cache_ttl_seconds).
# Cleared on every successful ingestion so stale answers are never served.
query_result_cache: dict[str, Any] = {}

# Job registry: keyed by job_id (hex uuid).
# Each value is a dict with: status, created_at, filename, user_id, file_hash,
# and optionally: started_at, completed_at, failed_at, error, result.
job_registry: dict[str, dict] = {}
