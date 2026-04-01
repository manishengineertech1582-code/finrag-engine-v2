"""
Query / Ask Endpoint
====================
POST /api/ask - grounded question answering with optional metadata filtering.

Compound prompts are normalized, split into focused clauses, retrieved clause by
clause, and then answered in a single final generation pass to reduce latency
and token usage.
"""

import logging
import re
import time
import uuid
from typing import Any, Iterable, List, Sequence

from fastapi import APIRouter, HTTPException

from app.services.patient_lookup import lookup_patient_rows
from app.state import pipeline_cache, query_result_cache
from config.settings import get_settings
from models.request import QueryRequest
from models.response import ChunkSource, QueryResponse, RetrievalMeta
from src.generator import answer_compound_question
from src.pipeline import load_pipeline, load_retriever_only

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["RAG"])

_MULTI_QUERY_MIN_WORDS = 5
_MULTI_QUERY_MIN_CHARS = 30
_INTENT_STARTERS = (
    "what",
    "who",
    "when",
    "where",
    "why",
    "how",
    "explain",
    "define",
    "describe",
    "list",
    "provide",
    "give",
    "show",
    "tell",
    "summarize",
    "summarise",
)
_INTENT_PATTERN = "(?:" + "|".join(_INTENT_STARTERS) + ")"
_SENTENCE_BOUNDARY_SPLIT = re.compile(
    rf"(?i)\s*[\.!?;,]+\s*(?=(?:and\s+)?{_INTENT_PATTERN}\b)"
)
_CONNECTOR_SPLIT = re.compile(
    rf"(?i)\s+(?:and\s+also|and\s+additionally|additionally|furthermore|moreover|plus|then)\s+(?={_INTENT_PATTERN}\b)"
)
_PLAIN_AND_SPLIT = re.compile(
    r"(?i)\s+and\s+(?=(?:what|who|explain|define|describe|list|provide|give|show|tell|summarize|summarise)\b)"
)
_PATIENT_COMPARISON_SPLIT = re.compile(
    r"(?i)\s+and\s+(?=(?:(?:list\s+of\s+)?(?:patient|patients)\s+)?(?:male|female|males|females)\b|(?:male|female|males|females)\s+patients?\b)"
)
_LEADING_CONNECTOR = re.compile(r"(?i)^(?:and|also|additionally|furthermore|moreover|plus|then)\s+")
_PATIENT_TERMS = re.compile(r"(?i)\b(patient|patients|male|female|males|females)\b")
_PATIENT_GENDER_PAIR = re.compile(r"(?i)\bmale[s]?\b")
_PATIENT_GENDER_PAIR_OTHER = re.compile(r"(?i)\bfemale[s]?\b")
_PATIENT_INFO_TYPO = re.compile(r"(?i)\bpatent\b\s+(?:info|details|data|records|list)\b")
_QUERY_NORMALIZATIONS = (
    (
        re.compile(
            r"(?i)\bpatent\b(?=\s+(?:info|details|data|records|list)\b.*\b(?:patients?|male|female|males|females)\b)"
        ),
        "patient",
    ),
    (re.compile(r"(?i)\bmales\b"), "male"),
    (re.compile(r"(?i)\bfemales\b"), "female"),
)



def _looks_like_patient_request(text: str) -> bool:
    lower = text.lower()
    has_subject = bool(_PATIENT_TERMS.search(text))
    has_request = any(
        token in lower
        for token in (
            "provide",
            "show",
            "give",
            "list",
            "info",
            "details",
            "data",
            "records",
            "living",
            "live",
            "lives",
            "stay",
            "stays",
            "staying",
            "from",
            "located",
            "reside",
            "resides",
            "residing",
            "doctor",
            "recovered",
            "under treatment",
        )
    )
    return has_subject and has_request



def _normalize_question(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question or "").strip()
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)

    if _looks_like_patient_request(normalized) or _PATIENT_INFO_TYPO.search(normalized):
        normalized = re.sub(r"(?i)\bpatent\b", "patient", normalized, count=1)

    for pattern, replacement in _QUERY_NORMALIZATIONS:
        normalized = pattern.sub(replacement, normalized)

    normalized = re.sub(
        r"(?i)\bfor\s+(male|female)\b(?=\s*$|[,.!?])",
        r"for \1 patients",
        normalized,
    )
    return normalized.strip()



def _clean_clause(clause: str) -> str:
    clause = _LEADING_CONNECTOR.sub("", clause.strip())
    clause = clause.strip(" ,.;:!?\t\r\n")
    clause = re.sub(r"\s+", " ", clause)
    return clause.strip()



def _derive_patient_prefix(clause: str) -> str:
    match = re.match(r"(?i)^(.*?\bfor\b)\s+", clause)
    if match and _looks_like_patient_request(clause):
        return match.group(1).strip()

    match = re.match(
        r"(?i)^((?:provide|give|show)\s+(?:patient\s+)?(?:info|details|data|records)|list\s+of\s+patients?|list\s+patients?)\b",
        clause,
    )
    if match:
        return match.group(1).strip()

    return "Provide patient info for"



def _split_patient_comparison_clause(clause: str) -> List[str]:
    cleaned = _clean_clause(clause)
    if not cleaned:
        return []

    if " and " not in cleaned.lower():
        return [cleaned]

    if not _looks_like_patient_request(cleaned):
        return [cleaned]

    if not (_PATIENT_GENDER_PAIR.search(cleaned) and _PATIENT_GENDER_PAIR_OTHER.search(cleaned)):
        return [cleaned]

    parts = [
        _clean_clause(part)
        for part in _PATIENT_COMPARISON_SPLIT.split(cleaned)
        if _clean_clause(part)
    ]
    if len(parts) <= 1:
        return [cleaned]

    prefix = _derive_patient_prefix(parts[0])
    expanded: List[str] = []
    for index, part in enumerate(parts):
        candidate = part
        if index > 0 and not re.match(rf"(?i)^{_INTENT_PATTERN}\b", part):
            candidate = f"{prefix} {part}"
        expanded.append(_normalize_question(candidate))
    return expanded



def _split_question_clauses(question: str) -> List[str]:
    normalized = _normalize_question(question)
    if not normalized:
        return []

    clauses: List[str] = []
    for part in _SENTENCE_BOUNDARY_SPLIT.split(normalized):
        for connector_split in _CONNECTOR_SPLIT.split(part):
            for clause_candidate in _PLAIN_AND_SPLIT.split(connector_split):
                patient_clauses = _split_patient_comparison_clause(clause_candidate)
                for patient_clause in patient_clauses:
                    clause = _clean_clause(patient_clause)
                    if clause:
                        clauses.append(clause)

    deduped: List[str] = []
    seen: set[str] = set()
    for clause in clauses:
        key = clause.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clause)
    return deduped



def _is_multi_intent_query(question: str) -> bool:
    return len(_split_question_clauses(question)) > 1



def _is_complex_query(question: str) -> bool:
    words = question.split()
    return len(words) >= _MULTI_QUERY_MIN_WORDS and len(question) >= _MULTI_QUERY_MIN_CHARS



def _should_use_multi_query(question: str, settings: Any) -> bool:
    return settings.use_multi_query and _is_complex_query(question) and not _looks_like_patient_request(question)



def _filters_for_request(request: QueryRequest) -> dict[str, Any]:
    filter_kwargs: dict[str, Any] = {}
    if request.user_id:
        filter_kwargs["user_id"] = request.user_id
    if request.doc_type_filter:
        filter_kwargs["doc_type"] = request.doc_type_filter
    if request.source_filter:
        filter_kwargs["source"] = request.source_filter
    return filter_kwargs



def _try_structured_patient_lookup(
    request: QueryRequest,
    question: str,
    settings: Any,
    *,
    max_results: int,
    log_routing: bool,
):
    if not _looks_like_patient_request(question):
        return None

    structured = lookup_patient_rows(
        question,
        upload_dir=settings.upload_dir,
        user_id=request.user_id,
        source_filter=request.source_filter,
        doc_type_filter=request.doc_type_filter,
        max_results=max_results,
    )
    if not structured.handled:
        return None

    if log_routing:
        logger.info(
            "Structured patient query routed | question='%s...' | matches=%d | returned_rows=%d | scanned_rows=%d | filters=%s",
            question[:80],
            structured.matched_rows,
            structured.returned_rows,
            structured.scanned_rows,
            structured.filters.as_log_dict(),
        )
    return structured



def _compose_structured_compound_answer(
    clauses: Sequence[str],
    structured_results: Sequence[Any],
) -> str:
    sections: list[str] = []
    for clause, result in zip(clauses, structured_results):
        sections.append(f"### {clause}\n{result.answer}")
    return "\n\n".join(sections)



def _build_pipeline(request: QueryRequest, use_multi_query: bool = True) -> Any:
    filter_kwargs = _filters_for_request(request)
    cache_key = f"qa|topk={request.top_k}|filters={sorted(filter_kwargs.items())}|mq={use_multi_query}"

    if cache_key not in pipeline_cache:
        logger.info("Building pipeline | key=%s", cache_key)
        try:
            pipeline_cache[cache_key] = load_pipeline(
                top_k=request.top_k,
                filter_kwargs=filter_kwargs or None,
                use_multi_query=use_multi_query,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Vector store not found. Upload at least one document via POST /api/ingest first.",
            ) from exc
        except Exception as exc:
            logger.exception("Pipeline initialisation failed.")
            raise HTTPException(
                status_code=503,
                detail="Pipeline failed to initialise. Check server logs.",
            ) from exc

    return pipeline_cache[cache_key]



def _build_retriever(request: QueryRequest, *, top_k: int, use_multi_query: bool = False) -> Any:
    filter_kwargs = _filters_for_request(request)
    cache_key = f"retriever|topk={top_k}|filters={sorted(filter_kwargs.items())}|mq={use_multi_query}"

    if cache_key not in pipeline_cache:
        logger.info("Building retriever | key=%s", cache_key)
        try:
            pipeline_cache[cache_key] = load_retriever_only(
                top_k=top_k,
                filter_kwargs=filter_kwargs or None,
                use_multi_query=use_multi_query,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Vector store not found. Upload at least one document via POST /api/ingest first.",
            ) from exc
        except Exception as exc:
            logger.exception("Retriever initialisation failed.")
            raise HTTPException(
                status_code=503,
                detail="Retriever failed to initialise. Check server logs.",
            ) from exc

    return pipeline_cache[cache_key]



def _build_source(doc: Any) -> ChunkSource:
    return ChunkSource(
        source=doc.metadata.get("source", "unknown"),
        page_or_sheet=doc.metadata.get("page_or_sheet", "unknown"),
        doc_type=doc.metadata.get("doc_type", "unknown"),
        chunk_id=doc.metadata.get("chunk_id", ""),
        user_id=doc.metadata.get("user_id"),
        snippet=(doc.page_content[:200] if hasattr(doc, "page_content") else None),
    )



def _dedupe_sources(sources: Iterable[ChunkSource]) -> List[ChunkSource]:
    deduped: List[ChunkSource] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source in sources:
        key = (source.source, source.page_or_sheet, source.doc_type, source.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped



def _invoke_pipeline(qa_chain: Any, question: str) -> tuple[str, List[ChunkSource], float]:
    t0 = time.perf_counter()
    result = qa_chain.invoke({"input": question})
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    answer = str(result.get("answer", "") or "").strip()
    context_docs = result.get("context", []) or []
    sources = [_build_source(doc) for doc in context_docs if hasattr(doc, "metadata")]
    return answer, sources, latency_ms



def _invoke_retriever(retriever: Any, question: str) -> tuple[List[Any], float]:
    t0 = time.perf_counter()
    docs = retriever.invoke(question) or []
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return list(docs), latency_ms



def _query_runtime(use_multi_query: bool, top_k: int, settings: Any) -> tuple[int, int]:
    queries_generated = settings.multi_query_num_queries if use_multi_query else 1
    candidates_before_rerank = min(top_k * 2, top_k + 4) if settings.use_hybrid_search else top_k
    return queries_generated, candidates_before_rerank



def _request_with_top_k(request: QueryRequest, top_k: int) -> QueryRequest:
    if request.top_k == top_k:
        return request
    return request.model_copy(update={"top_k": top_k})



def _derive_compound_top_k(request: QueryRequest, clause_count: int, settings: Any) -> int:
    configured = max(2, int(settings.compound_query_top_k))
    halved_budget = max(2, request.top_k // 2)
    if clause_count >= 4:
        halved_budget = max(2, request.top_k // 2)
    return max(2, min(request.top_k, configured, halved_budget))



def _run_single_question(
    request: QueryRequest,
    question: str,
    *,
    settings: Any,
    use_multi_query: bool,
) -> dict[str, Any]:
    structured = _try_structured_patient_lookup(
        request,
        question,
        settings,
        max_results=request.top_k,
        log_routing=True,
    )
    if structured is not None:
        return {
            "answer": structured.answer,
            "sources": structured.sources,
            "latency_ms": structured.latency_ms,
            "queries_generated": 1,
            "candidates_before_rerank": max(structured.scanned_rows, structured.matched_rows, 1),
            "multi_query_used": False,
            "compound_clause_count": 1,
            "confidence_override": _structured_confidence(structured),
        }

    qa_chain = _build_pipeline(request, use_multi_query=use_multi_query)
    answer, sources, latency_ms = _invoke_pipeline(qa_chain, question)
    queries_generated, candidates_before_rerank = _query_runtime(
        use_multi_query,
        request.top_k,
        settings,
    )
    return {
        "answer": answer or "This information is not available in the provided documents.",
        "sources": sources,
        "latency_ms": latency_ms,
        "queries_generated": queries_generated,
        "candidates_before_rerank": candidates_before_rerank,
        "multi_query_used": use_multi_query,
        "compound_clause_count": 1,
        "confidence_override": None,
    }



def _run_compound_question(
    request: QueryRequest,
    question: str,
    clauses: Sequence[str],
    settings: Any,
) -> dict[str, Any]:
    clause_top_k = _derive_compound_top_k(request, len(clauses), settings)
    focused_request = _request_with_top_k(request, clause_top_k)

    logger.info(
        "Compound query detected | clause_count=%d | top_k_per_clause=%d | clauses=%s",
        len(clauses),
        clause_top_k,
        list(clauses),
    )

    structured_clause_results = [
        _try_structured_patient_lookup(
            focused_request,
            clause,
            settings,
            max_results=clause_top_k,
            log_routing=False,
        )
        for clause in clauses
    ]
    all_structured = all(result is not None for result in structured_clause_results)
    retriever = None if all_structured else _build_retriever(focused_request, top_k=clause_top_k, use_multi_query=False)

    clause_contexts: list[tuple[str, list[Any]]] = []
    sources: List[ChunkSource] = []
    retrieval_latency_ms = 0.0
    candidates_before_rerank = 0

    for index, clause in enumerate(clauses, start=1):
        structured = structured_clause_results[index - 1]
        if structured is not None:
            logger.info(
                "Compound clause structured lookup | index=%d/%d | matches=%d | returned_rows=%d | scanned_rows=%d | clause='%s...'",
                index,
                len(clauses),
                structured.matched_rows,
                structured.returned_rows,
                structured.scanned_rows,
                clause[:80],
            )
            retrieval_latency_ms += structured.latency_ms
            candidates_before_rerank += max(structured.scanned_rows, structured.matched_rows, 1)
            clause_contexts.append((clause, structured.documents))
            sources.extend(structured.sources)
            continue

        logger.info(
            "Compound clause retrieval | index=%d/%d | top_k=%d | clause='%s...'",
            index,
            len(clauses),
            clause_top_k,
            clause[:80],
        )
        docs, clause_latency_ms = _invoke_retriever(retriever, clause)
        trimmed_docs = docs[:clause_top_k]
        retrieval_latency_ms += clause_latency_ms
        _, clause_candidates = _query_runtime(False, clause_top_k, settings)
        candidates_before_rerank += clause_candidates
        clause_contexts.append((clause, trimmed_docs))
        sources.extend(_build_source(doc) for doc in trimmed_docs if hasattr(doc, "metadata"))

    if all_structured:
        total_latency_ms = round(retrieval_latency_ms, 1)
        answer = _compose_structured_compound_answer(clauses, structured_clause_results)
        logger.info(
            "Compound answer generated via structured lookup | clauses=%d | total_ms=%.1f",
            len(clauses),
            total_latency_ms,
        )
        return {
            "answer": answer or "This information is not available in the provided documents.",
            "sources": _dedupe_sources(sources),
            "latency_ms": total_latency_ms,
            "queries_generated": len(clauses),
            "candidates_before_rerank": candidates_before_rerank,
            "multi_query_used": False,
            "compound_clause_count": len(clauses),
            "confidence_override": 0.96,
        }

    generation_started = time.perf_counter()
    answer = answer_compound_question(
        question,
        clause_contexts,
        model=settings.openai_model,
        max_tokens=settings.compound_answer_max_tokens,
    )
    generation_latency_ms = round((time.perf_counter() - generation_started) * 1000, 1)
    total_latency_ms = round(retrieval_latency_ms + generation_latency_ms, 1)

    logger.info(
        "Compound answer generated | clauses=%d | retrieval_ms=%.1f | generation_ms=%.1f | total_ms=%.1f",
        len(clauses),
        retrieval_latency_ms,
        generation_latency_ms,
        total_latency_ms,
    )

    return {
        "answer": answer or "This information is not available in the provided documents.",
        "sources": _dedupe_sources(sources),
        "latency_ms": total_latency_ms,
        "queries_generated": len(clauses),
        "candidates_before_rerank": candidates_before_rerank,
        "multi_query_used": False,
        "compound_clause_count": len(clauses),
        "confidence_override": None,
    }



def _run_query(
    request: QueryRequest,
    question: str,
    *,
    settings: Any,
    clauses: Sequence[str],
) -> dict[str, Any]:
    if len(clauses) > 1:
        return _run_compound_question(request, question, clauses, settings)

    use_multi_query = _should_use_multi_query(question, settings)
    return _run_single_question(
        request,
        question,
        settings=settings,
        use_multi_query=use_multi_query,
    )



def _confidence_score(source_count: int, top_k: int) -> float:
    raw_confidence = source_count / max(top_k, 1)
    return round(min(0.97, max(0.1, raw_confidence * 0.95)), 2)



def _structured_confidence(structured: Any) -> float:
    if structured.matched_rows <= 0:
        return 0.1

    filter_count = structured.filters.active_filter_count()
    confidence = 0.84 + (0.04 * filter_count)
    if structured.matched_rows == 1:
        confidence += 0.04
    if structured.matched_rows > structured.returned_rows:
        confidence -= 0.02
    return round(min(0.97, max(0.82, confidence)), 2)


@router.post(
    "/ask",
    response_model=QueryResponse,
    summary="Answer a question using the RAG pipeline",
)
async def ask_question(request: QueryRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    settings = get_settings()
    normalized_question = _normalize_question(question)
    if normalized_question != question:
        logger.info(
            "Query normalized | original='%s...' | normalized='%s...'",
            question[:80],
            normalized_question[:80],
        )

    clauses = _split_question_clauses(normalized_question)
    multi_intent = len(clauses) > 1
    use_multi_query = _should_use_multi_query(normalized_question, settings)
    if multi_intent:
        use_multi_query = False

    logger.info(
        "Query received | question='%s...' | user=%s | top_k=%d | mq=%s | multi_intent=%s | clauses=%d",
        normalized_question[:80],
        request.user_id,
        request.top_k,
        use_multi_query,
        multi_intent,
        max(len(clauses), 1),
    )

    cache_key = (
        f"q={normalized_question.lower()}"
        f"|user={request.user_id}"
        f"|src={request.source_filter}"
        f"|type={request.doc_type_filter}"
        f"|topk={request.top_k}"
    )
    ttl = settings.query_cache_ttl_seconds
    if ttl > 0 and cache_key in query_result_cache:
        entry = query_result_cache[cache_key]
        age = time.perf_counter() - entry["cached_at"]
        if age < ttl:
            logger.info("Query cache HIT | age=%.1fs | key=%s", age, cache_key[:80])
            cached_data = {**entry["response"], "request_id": uuid.uuid4().hex}
            return QueryResponse(**cached_data)
        del query_result_cache[cache_key]

    try:
        request_id = uuid.uuid4().hex
        result = _run_query(
            request,
            normalized_question,
            settings=settings,
            clauses=clauses or [normalized_question],
        )
        sources = _dedupe_sources(result["sources"])
        confidence_score = result.get("confidence_override") or _confidence_score(len(sources), request.top_k)
        retrieval_meta = RetrievalMeta(
            queries_generated=result["queries_generated"],
            candidates_before_rerank=result["candidates_before_rerank"],
            candidates_after_rerank=len(sources),
            hybrid_search=settings.use_hybrid_search,
            multi_query=result["multi_query_used"],
            latency_ms=result["latency_ms"],
            multi_intent_detected=multi_intent,
            compound_clause_count=result.get("compound_clause_count", 1),
        )

        logger.info(
            "Query answered | request_id=%s | sources=%d | confidence=%.2f | latency_ms=%.1f | user=%s",
            request_id,
            len(sources),
            confidence_score,
            result["latency_ms"],
            request.user_id,
        )

        response = QueryResponse(
            answer=result["answer"],
            sources=sources,
            total_chunks_retrieved=len(sources),
            confidence_score=confidence_score,
            retrieval_meta=retrieval_meta,
            request_id=request_id,
        )

        if ttl > 0:
            query_result_cache[cache_key] = {
                "response": response.model_dump(),
                "cached_at": time.perf_counter(),
            }

        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error processing query.")
        raise HTTPException(status_code=500, detail="Query processing failed.") from exc


