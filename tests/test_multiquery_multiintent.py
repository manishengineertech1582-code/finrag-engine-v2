"""
Compound-query and patient-query regression tests.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_caches():
    os.environ.setdefault('OPENAI_API_KEY', 'sk-test-placeholder')
    from config.settings import get_settings
    from app.state import pipeline_cache, query_result_cache

    get_settings.cache_clear()
    pipeline_cache.clear()
    query_result_cache.clear()
    yield
    pipeline_cache.clear()
    query_result_cache.clear()
    get_settings.cache_clear()



def _make_doc(
    *,
    source: str = 'report.pdf',
    location: str = 'page_1',
    doc_type: str = 'pdf',
    chunk_id: str = 'abc123',
):
    doc = MagicMock()
    doc.page_content = f'Content from {source}.'
    doc.metadata = {
        'source': source,
        'page_or_sheet': location,
        'doc_type': doc_type,
        'chunk_id': chunk_id,
        'user_id': None,
    }
    return doc



def _make_mock_result(answer: str = 'Test answer.'):
    return {'answer': answer, 'context': [_make_doc()]}


class TestMultiQueryPromptApproach:
    def _run_apply(self, num_queries: int):
        from src.retriever import _apply_multi_query, _get_multi_query_llm

        _get_multi_query_llm.cache_clear()
        captured: dict = {}

        def fake_from_llm(retriever, llm, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        with patch('langchain_openai.ChatOpenAI'):
            with patch(
                'langchain.retrievers.multi_query.MultiQueryRetriever.from_llm',
                side_effect=fake_from_llm,
            ):
                base = MagicMock()
                _apply_multi_query(base, 'gpt-4o-mini', num_queries=num_queries)

        _get_multi_query_llm.cache_clear()
        return captured

    def test_prompt_kwarg_passed_to_from_llm(self):
        captured = self._run_apply(2)
        assert 'prompt' in captured

    def test_num_queries_not_passed_to_from_llm(self):
        captured = self._run_apply(2)
        assert 'num_queries' not in captured

    def test_prompt_text_contains_requested_count(self):
        captured = self._run_apply(3)
        assert '3' in captured['prompt'].template


class TestQueryHeuristics:
    def _module(self):
        from app.routes import query as query_module
        return query_module

    def test_period_separated_prompt_is_multi_intent(self):
        question = (
            'Provide the list of patient Male who are from Chennai. '
            'and list of patient Female who are from Patna. '
            'What is transformer. What is statistics'
        )
        assert self._module()._is_multi_intent_query(question) is True

    def test_when_and_how_phrase_stays_single_intent(self):
        question = 'Explain when and how attention is computed in transformers'
        assert self._module()._is_multi_intent_query(question) is False

    def test_split_question_clauses_handles_reported_prompt(self):
        question = (
            'Provide patent info for Males patients . Explain what attention is ? , '
            'Provide Top 10 Must-Know Concepts Statistics Terms. What is deep learning'
        )
        assert self._module()._split_question_clauses(question) == [
            'Provide patient info for male patients',
            'Explain what attention is',
            'Provide Top 10 Must-Know Concepts Statistics Terms',
            'What is deep learning',
        ]

    def test_normalize_question_repairs_patient_typo_without_patients_word(self):
        normalized = self._module()._normalize_question('Provide patent info for Males')
        assert normalized == 'Provide patient info for male patients'

    def test_split_question_clauses_splits_patient_comparison_request(self):
        question = 'Provide patient info for Male living in Patna and female patient living in Pune'
        assert self._module()._split_question_clauses(question) == [
            'Provide patient info for Male living in Patna',
            'Provide patient info for female patient living in Pune',
        ]

    def test_patient_queries_skip_multi_query(self):
        settings = MagicMock(use_multi_query=True)
        assert self._module()._should_use_multi_query(
            'Provide patient info for Male living in Patna',
            settings,
        ) is False

    def test_compound_top_k_is_capped(self):
        from models.request import QueryRequest
        settings = MagicMock(compound_query_top_k=4)
        request = QueryRequest(question='q', top_k=8)
        assert self._module()._derive_compound_top_k(request, 4, settings) == 4


class TestQueryResponses:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        from app.state import pipeline_cache, query_result_cache

        pipeline_cache.clear()
        query_result_cache.clear()
        return TestClient(fastapi_app)

    def test_single_question_multi_intent_false(self):
        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result()

        client = self._client()
        with patch('app.routes.query._build_pipeline', return_value=chain):
            resp = client.post('/api/ask', json={'question': 'What are the key risk factors?', 'top_k': 8})
        assert resp.status_code == 200
        assert resp.json()['retrieval_meta']['multi_intent_detected'] is False
        assert resp.json()['retrieval_meta']['compound_clause_count'] == 1

    def test_patient_query_uses_single_query_without_multi_query(self):
        chain = MagicMock()
        chain.invoke.return_value = _make_mock_result('Male patient info.')

        client = self._client()
        with patch('app.routes.query._build_pipeline', return_value=chain) as build_pipeline:
            resp = client.post(
                '/api/ask',
                json={'question': 'Provide patient info for Male living in Patna', 'top_k': 8},
            )

        assert resp.status_code == 200
        assert resp.json()['retrieval_meta']['multi_query'] is False
        assert resp.json()['retrieval_meta']['queries_generated'] == 1
        assert build_pipeline.call_args.kwargs['use_multi_query'] is False

    def test_patient_comparison_query_uses_compound_path(self):
        retriever = MagicMock()
        retriever.invoke.side_effect = [
            [_make_doc(source='patients.csv', location='sheet_1', doc_type='csv', chunk_id='p1')],
            [_make_doc(source='patients.csv', location='sheet_1', doc_type='csv', chunk_id='p2')],
        ]

        client = self._client()
        with patch('app.routes.query._build_retriever', return_value=retriever) as build_retriever:
            with patch(
                'app.routes.query.answer_compound_question',
                return_value=(
                    '### Provide patient info for Male living in Patna\nMale patient info.\n\n'
                    '### Provide patient info for female patient living in Pune\nFemale patient info.'
                ),
            ) as compound_answer:
                with patch('app.routes.query._build_pipeline', side_effect=AssertionError('single-question pipeline should not run')):
                    resp = client.post(
                        '/api/ask',
                        json={
                            'question': 'Provide patient info for Male living in Patna and female patient living in Pune',
                            'top_k': 8,
                        },
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data['retrieval_meta']['multi_intent_detected'] is True
        assert data['retrieval_meta']['compound_clause_count'] == 2
        assert data['retrieval_meta']['multi_query'] is False
        assert retriever.invoke.call_count == 2
        assert compound_answer.call_count == 1
        assert build_retriever.call_args.kwargs['top_k'] == 4

    def test_compound_question_uses_single_generation_pass(self):
        retriever = MagicMock()
        retriever.invoke.side_effect = [
            [_make_doc(source='patients.csv', location='sheet_1', doc_type='csv', chunk_id='p1')],
            [_make_doc(source='attention.pdf', location='page_35', chunk_id='a1')],
            [_make_doc(source='statistics.pdf', location='page_9', chunk_id='s1')],
            [_make_doc(source='deep-learning.pdf', location='page_11', chunk_id='d1')],
        ]

        client = self._client()
        with patch('app.routes.query._build_retriever', return_value=retriever) as build_retriever:
            with patch(
                'app.routes.query.answer_compound_question',
                return_value=(
                    '### Provide patient info for male patients\nMale patient info is available.\n\n'
                    '### Explain what attention is\nAttention is a weighting mechanism.\n\n'
                    '### Provide Top 10 Must-Know Concepts Statistics Terms\n1. Mean\n2. Median\n3. Variance\n\n'
                    '### What is deep learning\nDeep learning uses multi-layer neural networks.'
                ),
            ) as compound_answer:
                with patch('app.routes.query._build_pipeline', side_effect=AssertionError('single-question pipeline should not run')):
                    resp = client.post(
                        '/api/ask',
                        json={
                            'question': (
                                'Provide patent info for Males patients . Explain what attention is ? , '
                                'Provide Top 10 Must-Know Concepts Statistics Terms. What is deep learning'
                            ),
                            'top_k': 8,
                        },
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data['retrieval_meta']['multi_intent_detected'] is True
        assert data['retrieval_meta']['multi_query'] is False
        assert data['retrieval_meta']['queries_generated'] == 4
        assert data['retrieval_meta']['compound_clause_count'] == 4
        assert data['total_chunks_retrieved'] == 4
        assert retriever.invoke.call_count == 4
        assert compound_answer.call_count == 1
        assert build_retriever.call_args.kwargs['top_k'] == 4


def _write_patient_csv(tmp_path, user_id: str = 'user-123', filename: str = 'patients.csv'):
    upload_dir = tmp_path / 'data' / 'raw' / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_text(
        'Patient_ID,Name,Age,Gender,Issue_Type,Doctor_Name,Department,Admission_Date,Discharge_Date,City,Country,Insurance_Provider,Severity,Outcome\n'
        'P0004,Simran Kaur,28,Female,Migraine,Dr. Nicole Kirkland,Neurology,1/6/2024,1/8/2024,Chennai,India,HealthPlus,Mild,Recovered\n'
        'P0001,Aarav Sharma,42,Male,Hypertension,Dr. Samuel Manning,Pulmonology,1/3/2024,1/7/2024,Delhi,India,HealthPlus,Moderate,Recovered\n'
        'P0016,Aditi Deshmukh,37,Female,Anxiety Disorder,Dr. Emily Carter,Psychiatry,1/18/2024,1/23/2024,Patna,India,HealthPlus,Moderate,Under Treatment\n',
        encoding='utf-8',
    )
    return file_path, tmp_path / 'data' / 'raw'



def _write_patient_csv_with_many_matches(tmp_path, user_id: str = 'user-123', filename: str = 'patients_many.csv'):
    upload_dir = tmp_path / 'data' / 'raw' / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_text(
        'Patient_ID,Name,Age,Gender,Issue_Type,Doctor_Name,Department,Admission_Date,Discharge_Date,City,Country,Insurance_Provider,Severity,Outcome\n'
        'P1001,Pooja Rao,31,Female,Asthma,Dr. Samuel Manning,Pulmonology,1/1/2024,1/5/2024,Delhi,India,HealthPlus,Moderate,Recovered\n'
        'P1002,Kavya Nair,29,Female,Migraine,Dr. Nicole Kirkland,Neurology,1/2/2024,1/6/2024,Mumbai,India,HealthPlus,Mild,Recovered\n'
        'P1003,Ritika Shah,44,Female,Diabetes,Dr. Emily Carter,Endocrinology,1/3/2024,1/8/2024,Patna,India,HealthPlus,Moderate,Recovered\n'
        'P1004,Meera Iyer,35,Female,Anxiety Disorder,Dr. Emily Carter,Psychiatry,1/4/2024,1/9/2024,Chennai,India,HealthPlus,Moderate,Recovered\n'
        'P1005,Sonal Verma,33,Female,Hypertension,Dr. Samuel Manning,Cardiology,1/5/2024,1/10/2024,Pune,India,HealthPlus,Moderate,Recovered\n'
        'P1006,Rohan Mehta,47,Male,Hypertension,Dr. Samuel Manning,Cardiology,1/6/2024,1/11/2024,Delhi,India,HealthPlus,Moderate,Recovered\n',
        encoding='utf-8',
    )
    return file_path, tmp_path / 'data' / 'raw'


class TestStructuredPatientLookup:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        from app.state import pipeline_cache, query_result_cache

        pipeline_cache.clear()
        query_result_cache.clear()
        return TestClient(fastapi_app)

    def test_lookup_matches_female_patient_by_city_phrase(self, tmp_path):
        _, upload_root = _write_patient_csv(tmp_path)
        from app.services.patient_lookup import lookup_patient_rows

        result = lookup_patient_rows(
            'Provide female patient details who stay in Chennai',
            upload_dir=str(upload_root),
            user_id='user-123',
        )

        assert result.handled is True
        assert result.matched_rows == 1
        assert result.returned_rows == 1
        assert result.filters.gender == 'Female'
        assert result.filters.city == 'Chennai'
        assert 'Simran Kaur' in result.answer
        assert result.sources[0].page_or_sheet == 'sheet_Sheet1_row_1'

    def test_single_patient_query_bypasses_generic_pipeline(self, tmp_path, monkeypatch):
        _, upload_root = _write_patient_csv(tmp_path)
        monkeypatch.setenv('UPLOAD_DIR', str(upload_root))

        from config.settings import get_settings
        get_settings.cache_clear()

        client = self._client()
        with patch('app.routes.query._build_pipeline', side_effect=AssertionError('generic pipeline should not run')):
            resp = client.post(
                '/api/ask',
                json={
                    'question': 'Provide female patient details who stay in Chennai',
                    'top_k': 8,
                    'user_id': 'user-123',
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert 'Simran Kaur' in data['answer']
        assert data['confidence_score'] == 0.96
        assert data['retrieval_meta']['multi_query'] is False
        assert data['retrieval_meta']['queries_generated'] == 1
        assert data['sources'][0]['page_or_sheet'] == 'sheet_Sheet1_row_1'

    def test_compound_patient_query_uses_structured_path_without_llm(self, tmp_path, monkeypatch):
        _, upload_root = _write_patient_csv(tmp_path)
        monkeypatch.setenv('UPLOAD_DIR', str(upload_root))

        from config.settings import get_settings
        get_settings.cache_clear()

        client = self._client()
        with patch('app.routes.query._build_pipeline', side_effect=AssertionError('generic pipeline should not run')):
            with patch('app.routes.query._build_retriever', side_effect=AssertionError('retriever should not run')):
                with patch('app.routes.query.answer_compound_question', side_effect=AssertionError('llm compound synthesis should not run')):
                    resp = client.post(
                        '/api/ask',
                        json={
                            'question': 'Provide female patient details who stay in Chennai and Provide Male patient details who have recovered',
                            'top_k': 8,
                            'user_id': 'user-123',
                        },
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data['confidence_score'] == 0.96
        assert data['total_chunks_retrieved'] == 2
        assert data['retrieval_meta']['compound_clause_count'] == 2
        assert '### Provide female patient details who stay in Chennai' in data['answer']
        assert 'Simran Kaur' in data['answer']
        assert 'Aarav Sharma' in data['answer']

    def test_compound_structured_patient_query_caps_clause_results(self, tmp_path, monkeypatch):
        _, upload_root = _write_patient_csv_with_many_matches(tmp_path)
        monkeypatch.setenv('UPLOAD_DIR', str(upload_root))

        from config.settings import get_settings
        get_settings.cache_clear()

        client = self._client()
        with patch('app.routes.query._build_pipeline', side_effect=AssertionError('generic pipeline should not run')):
            with patch('app.routes.query._build_retriever', side_effect=AssertionError('retriever should not run')):
                with patch('app.routes.query.answer_compound_question', side_effect=AssertionError('llm compound synthesis should not run')):
                    resp = client.post(
                        '/api/ask',
                        json={
                            'question': 'Provide female patient details who have recovered and Provide Male patient details who have recovered',
                            'top_k': 8,
                            'user_id': 'user-123',
                        },
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data['confidence_score'] == 0.96
        assert data['retrieval_meta']['compound_clause_count'] == 2
        assert data['total_chunks_retrieved'] == 5
        assert 'Pooja Rao' in data['answer']
        assert 'Meera Iyer' in data['answer']
        assert 'Rohan Mehta' in data['answer']
        assert 'Sonal Verma' not in data['answer']

    def test_compound_structured_patient_query_avoids_single_query_routing_log(self, tmp_path, monkeypatch):
        _, upload_root = _write_patient_csv_with_many_matches(tmp_path)
        monkeypatch.setenv('UPLOAD_DIR', str(upload_root))

        from config.settings import get_settings
        get_settings.cache_clear()

        client = self._client()
        with patch('app.routes.query._build_pipeline', side_effect=AssertionError('generic pipeline should not run')):
            with patch('app.routes.query._build_retriever', side_effect=AssertionError('retriever should not run')):
                with patch('app.routes.query.answer_compound_question', side_effect=AssertionError('llm compound synthesis should not run')):
                    with patch('app.routes.query.logger.info') as route_log:
                        resp = client.post(
                            '/api/ask',
                            json={
                                'question': 'Provide female patient details who have recovered and Provide Male patient details who have recovered',
                                'top_k': 8,
                                'user_id': 'user-123',
                            },
                        )

        assert resp.status_code == 200
        messages = [call.args[0] for call in route_log.call_args_list if call.args]
        assert any('Compound clause structured lookup' in message for message in messages)
        assert all('Structured patient query routed' not in message for message in messages)
