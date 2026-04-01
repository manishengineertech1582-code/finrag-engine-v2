"""
TXT Loader — Plain Text Documents
==================================
Strategy:
  - Auto-detect encoding (UTF-8 → Latin-1 → Windows-1252 fallback chain)
  - Normalize line endings and collapse excessive blank lines
  - Split on paragraph boundaries (double newlines) for semantic coherence
  - Further split oversized paragraphs at sentence boundaries

Metadata per Document:
  source, doc_type="txt", page_or_sheet="section_{n}", user_id

The resulting Documents are passed to chunk_documents() for final splitting.
"""

import logging
import os
import re
from typing import List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Encoding fallback chain — covers the vast majority of real-world text files
_ENCODINGS = ["utf-8-sig", "utf-8", "latin-1", "windows-1252"]

# Sections shorter than this are noise (headers, footers, blank lines)
_MIN_SECTION_CHARS = 40

# Split paragraphs that exceed this before handing to the chunker
_MAX_SECTION_CHARS = 3000


def load_txt(file_path: str, user_id: str | None = None) -> List[Document]:
    """Load a plain-text file and split it into paragraph-level Documents."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"TXT file not found: {file_path}")

    filename = os.path.basename(file_path)

    try:
        raw_text = _read_with_encoding_fallback(file_path, filename)
        sections = _split_into_sections(raw_text)

        documents: List[Document] = []
        for idx, section in enumerate(sections, start=1):
            text = section.strip()
            if len(text) < _MIN_SECTION_CHARS:
                continue
            documents.append(Document(
                page_content=text,
                metadata={
                    "source": filename,
                    "page_or_sheet": f"section_{idx}",
                    "doc_type": "txt",
                    "user_id": user_id,
                },
            ))

        logger.info("TXT loaded | sections=%d | file=%s", len(documents), filename)
        return documents

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.exception("Failed to load TXT: %s", file_path)
        raise RuntimeError(f"TXT load failed: {filename}") from e


def _read_with_encoding_fallback(file_path: str, filename: str) -> str:
    """Try each encoding in the fallback chain; raise ValueError if all fail."""
    for encoding in _ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding, errors="strict") as fh:
                text = fh.read()
            logger.debug("TXT decoded | encoding=%s | file=%s", encoding, filename)
            return text
        except (UnicodeDecodeError, LookupError):
            continue

    raise ValueError(
        f"Cannot decode '{filename}' with any of: {_ENCODINGS}. "
        "File may be binary or use an unsupported encoding."
    )


def _split_into_sections(text: str) -> List[str]:
    """
    Split text on double-newline paragraph boundaries.
    Paragraphs exceeding _MAX_SECTION_CHARS are further split at sentence ends.
    """
    # Normalize line endings, collapse 3+ blank lines to 2
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)

    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    sections: List[str] = []
    for para in raw_paragraphs:
        if len(para) <= _MAX_SECTION_CHARS:
            sections.append(para)
        else:
            # Split at sentence boundaries to keep semantic units intact
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current: List[str] = []
            current_len = 0
            for sentence in sentences:
                if current_len + len(sentence) + 1 > _MAX_SECTION_CHARS and current:
                    sections.append(" ".join(current))
                    current = [sentence]
                    current_len = len(sentence)
                else:
                    current.append(sentence)
                    current_len += len(sentence) + 1
            if current:
                sections.append(" ".join(current))

    return sections
