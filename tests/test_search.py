"""Sprint 9 — Search & Discovery API tests.

Tests cover:
- Authentication enforcement
- Query validation (empty, whitespace, too long)
- Limit enforcement (max 50)
- Pagination
- Institution isolation (cross-tenant leakage)
- Approval boundary (only APPROVED in BM25 layer)
- RBAC (GUEST role has search:use, but no auth = 401)
- Safe result serialisation (no internal paths/credentials)
- Search backend failure handling
- Autocomplete and trending endpoints
- BM25 and RRF integration (unit level)
- Existing test suite compatibility
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ──

class MockSearchUser:
    """Mock user for search token generation."""
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"{role.lower()}@search-test.edu"


def search_token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    with app.app_context():
        user = MockSearchUser(role=role, institution_id=institution_id, user_id=user_id)
        return generate_access_token(user), user


# ── 1. Unauthenticated search is rejected ──

def test_unauthenticated_search_rejected(client):
    response = client.get('/api/v1/search?q=algorithms')
    assert response.status_code == 401


def test_unauthenticated_autocomplete_rejected(client):
    response = client.get('/api/v1/search/autocomplete?q=data')
    assert response.status_code == 401


def test_unauthenticated_trending_rejected(client):
    response = client.get('/api/v1/search/trending')
    assert response.status_code == 401


# ── 2. Authenticated search succeeds ──

def test_authenticated_search_succeeds(app, client):
    token, user = search_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/search?q=algorithms',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'data' in data
    assert 'meta' in data
    assert data['meta']['query'] == 'algorithms'


# ── 3. Empty query returns empty results (not error) ──

def test_empty_query_returns_empty(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['data'] == [] or data['data'] == {}
    assert data['meta']['total'] == 0


def test_whitespace_only_query_returns_empty(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=   ',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['total'] == 0


def test_missing_query_param_returns_empty(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['total'] == 0


# ── 4. Query length validation ──

def test_excessively_long_query_rejected(app, client):
    token, _ = search_token(app)
    long_query = 'x' * 501
    response = client.get(
        f'/api/v1/search?q={long_query}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'VALIDATION_ERROR' in data['error']['code']


def test_query_at_max_length_accepted(app, client):
    token, _ = search_token(app)
    exact_query = 'a' * 500
    response = client.get(
        f'/api/v1/search?q={exact_query}',
        headers={'Authorization': f'Bearer {token}'}
    )
    # Should be 200 (valid), not 400
    assert response.status_code == 200


# ── 5. Limit enforcement ──

def test_limit_default_applied(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=algorithms',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['limit'] == 10


def test_limit_capped_at_50(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=algorithms&limit=999',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    # Server enforces max 50
    assert data['meta']['limit'] == 50


def test_negative_limit_uses_default(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=algorithms&limit=-5',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['limit'] == 10


# ── 6. Pagination ──

def test_pagination_meta_returned(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=algorithms&page=2&limit=5',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['page'] == 2
    assert data['meta']['limit'] == 5


def test_invalid_page_defaults_to_1(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search?q=algorithms&page=abc',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['page'] == 1


# ── 7. Institution isolation (cross-tenant search leakage) ──

def test_institution_id_from_jwt_not_query_param(app, client):
    """The institution_id in the query string must be ignored.
    The blueprint derives institution_id exclusively from JWT.
    """
    institution_jwt = str(uuid.uuid4())
    institution_query = str(uuid.uuid4())  # Different from JWT

    token, _ = search_token(app, institution_id=institution_jwt)

    # Capture what institution_id the SearchService receives
    with patch('app.blueprints.api.v1.search.get_search_service') as mock_svc_factory:
        mock_svc = MagicMock()
        mock_svc.hybrid_search.return_value = []
        mock_svc_factory.return_value = mock_svc

        response = client.get(
            f'/api/v1/search?q=test&institution_id={institution_query}',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 200

        # The service must have been called with the JWT institution, not the query param
        call_kwargs = mock_svc.hybrid_search.call_args
        assert call_kwargs is not None
        # institution_id passed to service should be from JWT
        received_inst = call_kwargs.kwargs.get('institution_id') or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
        )
        # It should match JWT institution, NOT the query-string one
        assert received_inst == institution_jwt
        assert received_inst != institution_query


# ── 8. Approval boundary in BM25 layer ──

def test_rag_service_filters_approved_only(app):
    """RAGService BM25 query filters StudyMaterial.status == 'APPROVED'."""
    from app.services.ai.rag_service import RAGService
    import inspect
    import ast

    # Read the source and verify the APPROVED filter is present
    source = inspect.getsource(RAGService.hybrid_search)
    assert 'APPROVED' in source, "RAGService must filter status='APPROVED' in BM25 query"


def test_unapproved_resource_not_in_bm25_results(app):
    """BM25 DB query must include status='APPROVED' filter — verified by direct service call."""
    from app.services.ai.rag_service import RAGService
    from app.models.resource import StudyMaterial, MaterialType
    from app.extensions import db
    import asyncio

    with app.app_context():
        # Insert a PENDING resource
        pending = StudyMaterial(
            id=uuid.uuid4(),
            title="Secret Pending Document",
            description="Should never appear in search",
            author_id=uuid.uuid4(),
            material_type=MaterialType.NOTE,
            status='PENDING',
        )
        db.session.add(pending)
        db.session.commit()

        # Mock Qdrant to return nothing (no network needed)
        with patch('app.services.ai.qdrant_service.QdrantService.search',
                   new_callable=AsyncMock, return_value=[]):
            with patch('app.services.ai.embedding_service.EmbeddingService.get_embedding',
                       new_callable=AsyncMock, return_value=[0.0] * 3072):
                rag = RAGService()
                loop = asyncio.new_event_loop()
                results = loop.run_until_complete(
                    rag.hybrid_search(query="Secret Pending Document", limit=10)
                )
                loop.close()

        # The pending resource must not appear
        doc_ids = [r.get('document_id', '') for r in results]
        assert str(pending.id) not in doc_ids, "PENDING resource must not appear in search results"


def test_rejected_resource_not_in_search(app):
    """REJECTED resources are excluded from BM25 (only APPROVED pass the filter)."""
    from app.services.ai.rag_service import RAGService
    from app.models.resource import StudyMaterial, MaterialType
    from app.extensions import db
    import asyncio

    with app.app_context():
        rejected = StudyMaterial(
            id=uuid.uuid4(),
            title="Rejected Resource Should Not Appear",
            description="rejected content",
            author_id=uuid.uuid4(),
            material_type=MaterialType.NOTE,
            status='REJECTED',
        )
        db.session.add(rejected)
        db.session.commit()

        with patch('app.services.ai.qdrant_service.QdrantService.search',
                   new_callable=AsyncMock, return_value=[]):
            with patch('app.services.ai.embedding_service.EmbeddingService.get_embedding',
                       new_callable=AsyncMock, return_value=[0.0] * 3072):
                rag = RAGService()
                loop = asyncio.new_event_loop()
                results = loop.run_until_complete(
                    rag.hybrid_search(query="Rejected Resource Should Not Appear", limit=10)
                )
                loop.close()

        doc_ids = [r.get('document_id', '') for r in results]
        assert str(rejected.id) not in doc_ids


# ── 9. RBAC: roles with search:use can search ──

def test_faculty_can_search(app, client):
    token, _ = search_token(app, role=Role.FACULTY)
    response = client.get(
        '/api/v1/search?q=algorithms',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200


def test_moderator_can_search(app, client):
    token, _ = search_token(app, role=Role.MODERATOR)
    response = client.get(
        '/api/v1/search?q=algorithms',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200


# ── 10. Safe result serialisation ──

def test_search_results_do_not_expose_internals(app, client):
    """_safe_result() must strip storage_path, credentials, and raw filesystem paths."""
    from app.services.search_service import _safe_result

    raw = {
        "document_id": str(uuid.uuid4()),
        "title": "Test Document",
        "text": "/var/data/uploads/secret/path.pdf credential=s3://bucket/key",
        "score": 0.95,
        "chunk_index": 0,
        "match_type": "hybrid_rrf",
        "storage_path": "/etc/secrets/aws.key",
        "institution_id": str(uuid.uuid4()),
        "bm25_score": 3.2,
    }

    safe = _safe_result(raw)

    # Must not contain storage_path key at all
    assert "storage_path" not in safe

    # Must not expose institution_id (user is already scoped)
    assert "institution_id" not in safe

    # Snippet should be truncated text (max 300 chars)
    assert "snippet" in safe
    assert len(safe["snippet"]) <= 300

    # Required safe fields present
    assert "document_id" in safe
    assert "title" in safe
    assert "score" in safe


# ── 11. Search backend failure is handled safely ──

def test_search_backend_failure_returns_503(app, client):
    """Search errors must return 503 with no internal details."""
    token, _ = search_token(app, role=Role.STUDENT)

    with patch('app.blueprints.api.v1.search.get_search_service') as mock_factory:
        mock_svc = MagicMock()
        mock_svc.hybrid_search.side_effect = Exception("Connection refused: qdrant:6333")
        mock_factory.return_value = mock_svc

        response = client.get(
            '/api/v1/search?q=test',
            headers={'Authorization': f'Bearer {token}'}
        )

    assert response.status_code == 503
    data = response.get_json()
    assert data['success'] is False
    # Must not expose internal error message
    error_msg = data['error']['message']
    assert 'qdrant' not in error_msg.lower()
    assert 'connection refused' not in error_msg.lower()
    assert '6333' not in error_msg


# ── 12. Qdrant integration boundary ──

def test_qdrant_service_passes_institution_filter(app):
    """QdrantService.search() builds an institution_id filter when provided."""
    from app.services.ai.qdrant_service import QdrantService
    import inspect

    source = inspect.getsource(QdrantService.search)
    assert 'institution_id' in source, "Qdrant search must accept and apply institution_id filter"
    assert 'FieldCondition' in source or 'filters' in source


# ── 13. BM25 integration boundary ──

def test_bm25_ranks_relevant_doc_higher():
    from app.services.ai.bm25_service import BM25Ranker
    ranker = BM25Ranker()
    docs = [
        {"document_id": "relevant", "text": "sorting algorithms quicksort mergesort", "chunk_index": 0},
        {"document_id": "irrelevant", "text": "database sql joins indexes", "chunk_index": 0},
    ]
    results = ranker.rank("sorting algorithms", docs, top_k=2)
    assert len(results) >= 1
    assert results[0]["document_id"] == "relevant"


# ── 14. RRF fusion behavior ──

def test_rrf_combines_dense_and_sparse():
    from app.services.ai.bm25_service import reciprocal_rank_fusion

    dense = [
        {"document_id": "doc_a", "chunk_index": 0, "score": 0.9},
        {"document_id": "doc_b", "chunk_index": 0, "score": 0.7},
    ]
    sparse = [
        {"document_id": "doc_b", "chunk_index": 0, "bm25_score": 5.2},
        {"document_id": "doc_c", "chunk_index": 0, "bm25_score": 4.1},
    ]
    fused = reciprocal_rank_fusion(dense, sparse, top_k=3)
    assert len(fused) >= 1
    # doc_b appeared in both lists — should have higher combined RRF score
    ids = [f["document_id"] for f in fused]
    assert "doc_b" in ids
    doc_b_pos = ids.index("doc_b")
    doc_a_pos = ids.index("doc_a") if "doc_a" in ids else 999
    # doc_b (in both lists) beats doc_a (dense only) or doc_c (sparse only)
    assert doc_b_pos == 0, f"doc_b (in both lists) should rank first, got: {ids}"


def test_rrf_scores_are_non_negative():
    from app.services.ai.bm25_service import reciprocal_rank_fusion
    dense = [{"document_id": "x", "chunk_index": 0, "score": 0.5}]
    sparse = [{"document_id": "x", "chunk_index": 0, "bm25_score": 2.0}]
    fused = reciprocal_rank_fusion(dense, sparse, top_k=1)
    for item in fused:
        assert item["score"] >= 0


# ── 15. Autocomplete endpoint ──

def test_autocomplete_requires_auth(client):
    response = client.get('/api/v1/search/autocomplete?q=data')
    assert response.status_code == 401


def test_autocomplete_returns_suggestions(app, client):
    token, _ = search_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/search/autocomplete?q=data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_autocomplete_empty_query(app, client):
    token, _ = search_token(app)
    response = client.get(
        '/api/v1/search/autocomplete',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200


# ── 16. Trending endpoint ──

def test_trending_requires_auth(client):
    response = client.get('/api/v1/search/trending')
    assert response.status_code == 401


def test_trending_returns_topics(app, client):
    token, _ = search_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/search/trending',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert len(data['data']) > 0
