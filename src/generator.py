"""
RAG Generator
=============
Builds the LLM-powered QA chains and focused compound-answer synthesis.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Iterable, Optional, Sequence, Tuple

from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DOCUMENT_PROMPT = PromptTemplate(
    template="[File: {source} | Location: {page_or_sheet}]\n{page_content}",
    input_variables=["page_content", "source", "page_or_sheet"],
)

SYSTEM_PROMPT = """You are FinRAG, an expert document assistant.

Answer the user's question using ONLY the provided context passages.
Each passage starts with a [File: X | Location: Y] label that must be used for citations.

Rules:
1. Be concise and direct. Prefer a short paragraph or a compact list.
2. Use only supported facts from the context.
3. Cite every factual claim as [source: <filename>, <location>].
4. If the context does not contain the answer, say exactly: This information is not available in the provided documents.
5. Preserve exact figures, names, and terminology from the source.

Context passages:
{context}"""

PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{input}"),
])

COMPOUND_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are FinRAG, an expert document assistant.

You will receive several focused questions, each with its own context block.
Answer each question in its own markdown heading using the exact question text.
Use only the context attached to that question.

Rules:
1. Format every section as: ### <question>.
2. Keep each section concise. Use short paragraphs or a compact numbered list when the question asks for key concepts or top terms.
3. Cite every factual statement as [source: <filename>, <location>].
4. If a section's context is insufficient, say exactly: This information is not available in the provided documents.
5. Do not mix evidence between sections.
""",
    ),
    (
        "human",
        "Original user request:\n{question}\n\nFocused question blocks:\n{compound_context}",
    ),
])


@lru_cache(maxsize=8)
def _get_chat_llm(model: str, temperature: float, max_tokens: Optional[int]):
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "timeout": 45,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


_retry = retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)


@_retry
def _invoke_llm(prompt: ChatPromptTemplate, *, model: str, temperature: float, max_tokens: Optional[int], **kwargs: Any):
    llm = _get_chat_llm(model, temperature, max_tokens)
    messages = prompt.format_messages(**kwargs)
    return llm.invoke(messages)



def _format_document(doc: Document) -> str:
    return DOCUMENT_PROMPT.format(
        page_content=doc.page_content,
        source=doc.metadata.get("source", "unknown"),
        page_or_sheet=doc.metadata.get("page_or_sheet", "unknown"),
    )



def _format_compound_context(clause_contexts: Sequence[Tuple[str, Sequence[Document]]]) -> str:
    sections: list[str] = []
    for index, (clause, docs) in enumerate(clause_contexts, start=1):
        rendered_docs = [
            _format_document(doc)
            for doc in docs
        ]
        context_block = "\n\n".join(rendered_docs) if rendered_docs else "No relevant context retrieved."
        sections.append(
            f"Question {index}: {clause}\nContext:\n{context_block}"
        )
    return "\n\n---\n\n".join(sections)



def build_qa_chain(
    retriever: Any,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> Any:
    """Assemble the full retrieval chain for single-question answers."""
    if retriever is None:
        raise ValueError("retriever cannot be None.")

    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    logger.info(
        "Building QA chain | model=%s | temperature=%.2f | max_tokens=%s",
        model_name,
        temperature,
        max_tokens,
    )

    llm = _get_chat_llm(model_name, temperature, max_tokens)
    combine_docs_chain = create_stuff_documents_chain(
        llm,
        PROMPT,
        document_prompt=DOCUMENT_PROMPT,
    )
    qa_chain = create_retrieval_chain(retriever, combine_docs_chain)

    logger.info("QA chain built successfully.")
    return qa_chain



def answer_compound_question(
    question: str,
    clause_contexts: Sequence[Tuple[str, Sequence[Document]]],
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    """Answer a compound query with one grounded generation pass."""
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    compound_context = _format_compound_context(clause_contexts)
    logger.info(
        "Generating compound answer | model=%s | clauses=%d | max_tokens=%s",
        model_name,
        len(clause_contexts),
        max_tokens,
    )
    result = _invoke_llm(
        COMPOUND_PROMPT,
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        question=question,
        compound_context=compound_context,
    )
    content = getattr(result, "content", "")
    return str(content or "").strip()
