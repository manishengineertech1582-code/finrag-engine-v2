"""
Request Schemas
================
Pydantic v2 models validated by FastAPI on every inbound request.
Includes basic prompt injection detection on the question field.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Patterns that signal prompt injection attempts.
# Using a short-circuit allowlist approach: flag only unambiguous attack patterns.
_INJECTION_PATTERNS = re.compile(
    r"(?i)(?:"
    r"ignore\s+(all\s+)?previous\s+instructions?"
    r"|disregard\s+(all\s+)?(previous|prior)"
    r"|forget\s+(all\s+)?(previous|prior)"
    r"|you\s+are\s+now\s+(?:an?\s+)?\w+"
    r"|<\s*(?:system|assistant|user)\s*>"
    r")"
)


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User query (plain natural language)",
    )
    user_id: Optional[str] = Field(
        None,
        description="User/tenant ID — restricts retrieval to this user's documents",
    )
    source_filter: Optional[str] = Field(
        None,
        description="Filter retrieval to a specific filename",
    )
    doc_type_filter: Optional[Literal["pdf", "docx", "excel", "csv", "txt"]] = Field(
        None,
        description="Filter retrieval to a document type",
    )
    top_k: int = Field(
        8,
        ge=1,
        le=20,
        description="Number of chunks to retrieve (1–20)",
    )

    @field_validator("question")
    @classmethod
    def _guard_prompt_injection(cls, v: str) -> str:
        if _INJECTION_PATTERNS.search(v):
            raise ValueError(
                "Question contains disallowed content. "
                "Please ask a factual question about your documents."
            )
        return v.strip()
