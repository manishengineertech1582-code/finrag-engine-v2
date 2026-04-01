"""
create_index.py
================
CLI script to build the FAISS vector store from a directory of documents.

Usage:
    python create_index.py                        # indexes all docs in data/raw/
    python create_index.py --dir path/to/docs
    python create_index.py --dir data/ --user-id team_a
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv"}


def main():
    parser = argparse.ArgumentParser(description="Build FAISS vector store from documents.")
    parser.add_argument("--dir", default="data/raw", help="Directory with documents")
    parser.add_argument("--user-id", default=None, help="User/tenant ID to tag documents")
    parser.add_argument("--vectorstore", default=os.getenv("VECTORSTORE_PATH", "vector_store"))
    args = parser.parse_args()

    doc_dir = args.dir
    if not os.path.isdir(doc_dir):
        logger.error("Directory not found: %s", doc_dir)
        sys.exit(1)

    files = [
        os.path.join(doc_dir, f)
        for f in os.listdir(doc_dir)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        logger.error("No supported documents found in: %s", doc_dir)
        sys.exit(1)

    logger.info("Found %d document(s) to index.", len(files))

    from src.chunking import chunk_documents
    from src.embeddings import add_to_vector_store
    from src.ingestion.factory import load_document
    from src.metadata import enrich_chunks

    all_chunks = []
    for path in files:
        try:
            docs = load_document(path, user_id=args.user_id)
            chunks = chunk_documents(docs)
            chunks = enrich_chunks(chunks, user_id=args.user_id)
            all_chunks.extend(chunks)
            logger.info("OK: %s -> %d chunks", os.path.basename(path), len(chunks))
        except Exception as e:
            logger.warning("SKIP: %s: %s", path, e)

    if not all_chunks:
        logger.error("No chunks generated. Exiting.")
        sys.exit(1)

    os.makedirs(args.vectorstore, exist_ok=True)
    add_to_vector_store(all_chunks, persist_path=args.vectorstore)
    logger.info("Index built | total_chunks=%d | path=%s", len(all_chunks), args.vectorstore)


if __name__ == "__main__":
    main()
