"""
Embeddings & Vector Store
==========================
Manages FAISS index lifecycle: build, incremental add, load.

Key design:
  - FileLock around all write operations — safe for concurrent ingestion
  - Batch processing (200 docs/batch) — stays under OpenAI's 300k token/req limit
  - Checkpoint save after every batch — safe restart after interruption
  - SHA256 file registry — prevents duplicate ingestion of identical content
  - Single FAISS.from_documents() on first batch (avoids pickle memo bug)
"""

import json
import logging
import os
from typing import List, Optional

import filelock
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

load_dotenv()
logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 200   # Safe batch size — well under OpenAI's 300k token limit
_LOCK_TIMEOUT = 60       # seconds to wait for write lock before raising
_REGISTRY_FILENAME = "ingested_files.json"


# ── Embeddings ────────────────────────────────────────────────────────────────

def get_embeddings(model: str = "text-embedding-3-small") -> OpenAIEmbeddings:
    """Return a configured OpenAI embeddings model."""
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY is not set.")
    return OpenAIEmbeddings(model=model)


# ── Vector Store ──────────────────────────────────────────────────────────────

def build_vector_store(
    chunks: List[Document],
    persist_path: str = "vector_store",
    embedding_model: str = "text-embedding-3-small",
) -> FAISS:
    """
    Build a FAISS index from scratch and persist to disk.
    Uses FileLock to prevent concurrent write corruption.
    """
    if not chunks:
        raise ValueError("Cannot build vector store from empty chunk list.")

    embeddings = get_embeddings(embedding_model)
    lock_path = _lock_path(persist_path)
    os.makedirs(persist_path, exist_ok=True)

    logger.info("Building vector store | chunks=%d | model=%s", len(chunks), embedding_model)

    batches = [chunks[i: i + EMBED_BATCH_SIZE] for i in range(0, len(chunks), EMBED_BATCH_SIZE)]
    total_batches = len(batches)

    with filelock.FileLock(lock_path, timeout=_LOCK_TIMEOUT):
        vectorstore: Optional[FAISS] = None
        for idx, batch in enumerate(batches, start=1):
            logger.info("Batch %d/%d | chunks=%d", idx, total_batches, len(batch))
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, embeddings)
            else:
                vectorstore.add_documents(batch)
            vectorstore.save_local(persist_path)

    logger.info("Vector store saved | path=%s | total_docs=%d", persist_path, len(chunks))
    return vectorstore  # type: ignore[return-value]


def add_to_vector_store(
    new_chunks: List[Document],
    persist_path: str = "vector_store",
    embedding_model: str = "text-embedding-3-small",
) -> FAISS:
    """
    Append new chunks to an existing FAISS index (incremental ingestion).
    Creates a new index if none exists yet.
    FileLock prevents race conditions in concurrent ingestion scenarios.
    """
    if not new_chunks:
        raise ValueError("No chunks to add.")

    embeddings = get_embeddings(embedding_model)
    lock_path = _lock_path(persist_path)
    index_file = os.path.join(persist_path, "index.faiss")
    os.makedirs(persist_path, exist_ok=True)

    batches = [new_chunks[i: i + EMBED_BATCH_SIZE] for i in range(0, len(new_chunks), EMBED_BATCH_SIZE)]
    total_batches = len(batches)
    logger.info(
        "Embedding %d chunks in %d batch(es) | model=%s",
        len(new_chunks), total_batches, embedding_model,
    )

    with filelock.FileLock(lock_path, timeout=_LOCK_TIMEOUT):
        vectorstore: Optional[FAISS] = None

        if os.path.exists(index_file):
            logger.info("Loading existing vector store from %s", persist_path)
            vectorstore = FAISS.load_local(
                persist_path, embeddings, allow_dangerous_deserialization=True
            )

        for idx, batch in enumerate(batches, start=1):
            logger.info("Batch %d/%d | chunks=%d", idx, total_batches, len(batch))
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, embeddings)
            else:
                vectorstore.add_documents(batch)
            # Checkpoint after every batch — safe restart if interrupted
            vectorstore.save_local(persist_path)

    logger.info(
        "Vector store updated | path=%s | new_chunks=%d",
        persist_path, len(new_chunks),
    )
    return vectorstore  # type: ignore[return-value]


def load_vector_store(
    persist_path: str = "vector_store",
    embedding_model: str = "text-embedding-3-small",
) -> FAISS:
    """Load an existing FAISS index from disk."""
    index_file = os.path.join(persist_path, "index.faiss")
    if not os.path.exists(index_file):
        raise FileNotFoundError(
            f"Vector store not found at '{persist_path}'. "
            "Run the ingestion pipeline first (POST /api/ingest or create_index.py)."
        )
    embeddings = get_embeddings(embedding_model)
    return FAISS.load_local(
        persist_path, embeddings, allow_dangerous_deserialization=True
    )


# ── Deduplication Registry ────────────────────────────────────────────────────

def load_document_registry(persist_path: str) -> dict:
    """
    Return the full ingestion registry as a plain dict.

    Keys are "{user_id}:{file_hash}", values are metadata dicts with
    filename, doc_type, chunks_indexed, ingested_at.
    Returns {} if no registry file exists yet.
    """
    return _load_registry(persist_path)


def is_duplicate_file(file_hash: str, user_id: str | None, persist_path: str) -> bool:
    """Return True if this exact file content has already been ingested for this user."""
    registry = _load_registry(persist_path)
    return _registry_key(file_hash, user_id) in registry


def register_file(
    file_hash: str,
    user_id: str | None,
    metadata: dict,
    vectorstore_path: str,
) -> None:
    """Record a successfully ingested file so duplicates can be rejected."""
    lock_path = _lock_path(vectorstore_path)
    with filelock.FileLock(lock_path, timeout=_LOCK_TIMEOUT):
        registry = _load_registry(vectorstore_path)
        registry[_registry_key(file_hash, user_id)] = metadata
        _save_registry(registry, vectorstore_path)


def _registry_key(file_hash: str, user_id: str | None) -> str:
    return f"{user_id or '__global__'}:{file_hash}"


def _registry_path(persist_path: str) -> str:
    return os.path.join(persist_path, _REGISTRY_FILENAME)


def _lock_path(persist_path: str) -> str:
    return os.path.join(persist_path, ".write.lock")


def _load_registry(persist_path: str) -> dict:
    path = _registry_path(persist_path)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("Registry file corrupted or unreadable — starting fresh.")
    return {}


def _save_registry(registry: dict, persist_path: str) -> None:
    os.makedirs(persist_path, exist_ok=True)
    with open(_registry_path(persist_path), "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2)
