"""
Base Loader Protocol
=====================
Defines the contract that ALL format-specific loaders must implement.
This enables the factory to swap loaders without changing the pipeline.
"""

from typing import List, Protocol, runtime_checkable
from langchain_core.documents import Document


@runtime_checkable
class DocumentLoader(Protocol):
    """Protocol (interface) every loader must satisfy."""

    def load(self, file_path: str, user_id: str | None = None) -> List[Document]:
        """
        Load a file and return a list of LangChain Documents.

        Each Document must have:
            page_content : str  — extracted text
            metadata     : dict — rich metadata dict (see metadata.py)
        """
        ...
