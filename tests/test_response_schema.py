"""
Response schema regression tests.
"""

from models.response import ChunkSource, QueryResponse, RetrievalMeta


class TestChunkSourceSnippet:
    def test_snippet_field_exists(self):
        src = ChunkSource(
            source='report.pdf',
            page_or_sheet='page 3',
            doc_type='pdf',
            chunk_id='abc123',
            snippet='Revenue increased by 12 percent year-over-year in Q3 2024.',
        )
        assert src.snippet == 'Revenue increased by 12 percent year-over-year in Q3 2024.'

    def test_snippet_defaults_to_none(self):
        src = ChunkSource(
            source='doc.txt',
            page_or_sheet='para 1',
            doc_type='txt',
            chunk_id='xyz',
        )
        assert src.snippet is None


class TestRetrievalMeta:
    def test_fields_present(self):
        meta = RetrievalMeta(
            queries_generated=3,
            candidates_before_rerank=8,
            candidates_after_rerank=5,
            hybrid_search=True,
            multi_query=True,
            compound_clause_count=4,
        )
        assert meta.queries_generated == 3
        assert meta.candidates_before_rerank == 8
        assert meta.candidates_after_rerank == 5
        assert meta.hybrid_search is True
        assert meta.multi_query is True
        assert meta.compound_clause_count == 4

    def test_defaults_are_safe(self):
        meta = RetrievalMeta()
        assert meta.queries_generated == 1
        assert meta.candidates_before_rerank == 0
        assert meta.candidates_after_rerank == 0
        assert meta.hybrid_search is False
        assert meta.multi_query is False
        assert meta.compound_clause_count == 1

    def test_serialises_to_dict(self):
        meta = RetrievalMeta(
            queries_generated=1,
            candidates_before_rerank=8,
            candidates_after_rerank=8,
            compound_clause_count=2,
        )
        dumped = meta.model_dump()
        assert 'queries_generated' in dumped
        assert dumped['compound_clause_count'] == 2


class TestQueryResponseRetrievalMeta:
    def test_retrieval_meta_field_exists(self):
        meta = RetrievalMeta(
            queries_generated=3,
            candidates_before_rerank=12,
            candidates_after_rerank=6,
            hybrid_search=True,
            multi_query=True,
            compound_clause_count=3,
        )
        resp = QueryResponse(
            answer='Revenue grew 12 percent.',
            sources=[],
            total_chunks_retrieved=6,
            confidence_score=0.85,
            retrieval_meta=meta,
        )
        assert resp.retrieval_meta is not None
        assert resp.retrieval_meta.queries_generated == 3
        assert resp.retrieval_meta.hybrid_search is True
        assert resp.retrieval_meta.compound_clause_count == 3

    def test_retrieval_meta_defaults_to_none(self):
        resp = QueryResponse(
            answer='Answer here.',
            sources=[],
            total_chunks_retrieved=0,
            confidence_score=0.5,
        )
        assert resp.retrieval_meta is None

    def test_full_serialisation_round_trip(self):
        import json

        meta = RetrievalMeta(
            queries_generated=3,
            candidates_before_rerank=8,
            candidates_after_rerank=5,
            hybrid_search=True,
            multi_query=True,
            compound_clause_count=4,
        )
        resp = QueryResponse(
            answer='Test answer.',
            sources=[],
            total_chunks_retrieved=5,
            confidence_score=0.72,
            retrieval_meta=meta,
        )
        serialised = json.loads(resp.model_dump_json())
        assert serialised['retrieval_meta']['queries_generated'] == 3
        assert serialised['retrieval_meta']['hybrid_search'] is True
        assert serialised['retrieval_meta']['compound_clause_count'] == 4
        assert serialised['confidence_score'] == 0.72
