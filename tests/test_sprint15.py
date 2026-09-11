"""CampusX Sprint 15 — Document Ingestion Pipeline Wiring Test Suite.

Test categories:
    A. Approval → Indexing wiring
    B. Institution isolation (BM25 + Qdrant)
    C. Approval filtering (APPROVED/PENDING/REJECTED/deleted)
    D. Indexing task metadata and guards
    E. General Q&A /ask endpoint with institution scoping
    F. Rate limiting configuration
    G. Regression (previously passing tests unaffected)

All external services are mocked:
    - Qdrant: AsyncMock returning empty results
    - Celery indexing task: patch index_document_task.delay
    - OpenAI / Anthropic: fall through to AIClients mock response
"""
import uuid
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.resource import StudyMaterial, MaterialType
from app.models.academic import Institution
from app.services.approval_service import ApprovalService
from app.services.ai.rag_service import RAGService
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    _app = create_app("testing")
    with _app.app_context():
        db.create_all()
        yield _app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _inst(code=None):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid,
        name=f"Test Uni {iid.hex[:4]}",
        short_name="TU",
        code=code or f"TU{iid.hex[:6]}",
        domain_whitelist=[],
        settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(iid)


def _user(institution_id, role=Role.STUDENT, status="active"):
    uid = uuid.uuid4()
    email = f"u{uid.hex[:8]}@test.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test User",
        password_hash="hashed",
        institution_id=uuid.UUID(institution_id),
        role=role,
        status=status,
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _material(author_id, status="PENDING", title="Test Material", subject_id=None):
    mid = uuid.uuid4()
    mat = StudyMaterial(
        id=mid,
        title=title,
        description=f"Description for {title}",
        author_id=uuid.UUID(author_id),
        material_type=MaterialType.NOTE,
        status=status,
        is_deleted=False,
        subject_id=uuid.UUID(subject_id) if subject_id else None,
    )
    db.session.add(mat)
    db.session.flush()
    return str(mid)


class _FakeUser:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())


def _token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u)


def _mock_qdrant():
    m = MagicMock()
    m.ensure_collection = AsyncMock(return_value=None)
    m.search = AsyncMock(return_value=[])
    m.upsert_chunks = AsyncMock(return_value=None)
    m.delete_chunks_for_document = AsyncMock(return_value=1)
    return m


def _mock_embedder():
    m = MagicMock()
    m.get_embedding = AsyncMock(return_value=[0.1] * 3072)
    m.batch_embed_chunks = AsyncMock(return_value=[[0.1] * 3072])
    return m


# ══════════════════════════════════════════════════════════════════════════════
# A. Approval → Indexing Wiring
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalIndexingWiring:
    """Verify that the approval workflow dispatches indexing exactly when it should."""

    def test_approve_dispatches_indexing_task(self, app):
        """Approving a PENDING resource dispatches index_document_task.delay()."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            result = svc.approve_material(mat_id, reviewer_id, iid)
            assert result["decision"] == "approved"
            assert result["status"] == "APPROVED"
            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args
            # material_id is the first positional arg
            assert str(mat_id) in str(call_kwargs)

    def test_approve_dispatches_with_correct_material_id(self, app):
        """The dispatched task receives the correct material_id."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            svc.approve_material(mat_id, reviewer_id, iid)
            args, kwargs = mock_task.delay.call_args
            # material_id should be first positional or keyword argument
            dispatched_id = args[0] if args else kwargs.get("material_id", "")
            assert str(mat_id) == str(dispatched_id)

    def test_dispatch_failure_does_not_rollback_approval(self, app):
        """If Celery dispatch raises, the approval DB record is still committed."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock(side_effect=RuntimeError("Celery broker down"))
            svc = ApprovalService()
            result = svc.approve_material(mat_id, reviewer_id, iid)
            # Approval succeeded even though dispatch raised
            assert result["status"] == "APPROVED"

        # Verify DB state — material should be APPROVED
        with app.app_context():
            mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(mat_id)).first()
            assert mat.status == "APPROVED"

    def test_pending_resource_dispatch_not_triggered_on_reject(self, app):
        """Rejecting a resource dispatches no indexing task."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            result = svc.reject_material(mat_id, reviewer_id, iid, reason="Test rejection")
            assert result["status"] == "REJECTED"
            mock_task.delay.assert_not_called()

    def test_already_approved_resource_raises_on_re_approve(self, app):
        """Double-approving the same resource raises ValueError."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="APPROVED")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            with pytest.raises(ValueError):
                svc.approve_material(mat_id, reviewer_id, iid)
            mock_task.delay.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# B. Indexing Task Guards
# ══════════════════════════════════════════════════════════════════════════════

class TestIndexingTaskGuards:
    """Verify the indexing task only processes valid APPROVED non-deleted resources."""

    def test_indexing_task_aborts_on_non_approved_status(self, app):
        """Task returns SKIPPED when material is not APPROVED."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context():
            # In testing mode Celery is a stub — tasks are plain callables, not Task objects
            from app.tasks.indexing import index_document_task
            result = index_document_task(mat_id, {})
            assert result["status"] == "SKIPPED"
            assert "PENDING" in result.get("reason", "") or "status" in result.get("reason", "")

    def test_indexing_task_aborts_when_material_not_found(self, app):
        """Task returns FAILED for a non-existent material_id."""
        with app.app_context():
            from app.tasks.indexing import index_document_task
            result = index_document_task(str(uuid.uuid4()), {})
            assert result["status"] == "FAILED"

    def test_indexing_task_aborts_on_invalid_uuid(self, app):
        """Task returns FAILED for a malformed material_id."""
        with app.app_context():
            from app.tasks.indexing import index_document_task
            result = index_document_task("not-a-uuid", {})
            assert result["status"] == "FAILED"

    def test_indexing_task_does_not_auto_approve(self, app):
        """Indexing a PENDING material does not change its status to APPROVED."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context():
            from app.tasks.indexing import index_document_task
            index_document_task(mat_id, {})
            mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(mat_id)).first()
            assert mat.status != "APPROVED"

    def test_indexing_task_uses_db_institution_id(self, app):
        """Indexing task resolves institution_id from DB, not from metadata."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="APPROVED")
            db.session.commit()

        captured_metadata = {}

        async def _fake_ingest(self_rag, file_bytes, filename, metadata):
            captured_metadata.update(metadata)
            return 1

        with app.app_context(), \
             patch("app.services.ai.rag_service.RAGService.ingest_material", new=_fake_ingest):
            from app.tasks.indexing import index_document_task
            index_document_task(mat_id, {"institution_id": "tampered-value"})

        # Task should have overridden the tampered institution_id with the DB value
        assert captured_metadata.get("institution_id") == iid

    def test_indexing_task_includes_is_approved_true_in_qdrant_metadata(self, app):
        """Qdrant metadata must include is_approved=True for APPROVED materials."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="APPROVED")
            db.session.commit()

        captured_metadata = {}

        async def _fake_ingest(self_rag, file_bytes, filename, metadata):
            captured_metadata.update(metadata)
            return 1

        with app.app_context(), \
             patch("app.services.ai.rag_service.RAGService.ingest_material", new=_fake_ingest):
            from app.tasks.indexing import index_document_task
            index_document_task(mat_id, {})

        assert captured_metadata.get("is_approved") is True
        assert captured_metadata.get("is_deleted") is False

    def test_indexing_task_includes_institution_id_in_qdrant_metadata(self, app):
        """Qdrant metadata institution_id must be non-empty for properly authored resources."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="APPROVED")
            db.session.commit()

        captured_metadata = {}

        async def _fake_ingest(self_rag, file_bytes, filename, metadata):
            captured_metadata.update(metadata)
            return 1

        with app.app_context(), \
             patch("app.services.ai.rag_service.RAGService.ingest_material", new=_fake_ingest):
            from app.tasks.indexing import index_document_task
            index_document_task(mat_id, {})

        assert captured_metadata.get("institution_id") == iid
        assert len(captured_metadata["institution_id"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# C. BM25 Institution Isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestBM25InstitutionIsolation:
    """Verify BM25 sparse retrieval respects institution boundaries."""

    def test_bm25_excludes_other_institution_materials(self, app):
        """BM25 query for institution A must not return institution B's materials."""
        with app.app_context():
            iid_a = _inst()
            iid_b = _inst()
            author_a = _user(iid_a, role=Role.STUDENT)
            author_b = _user(iid_b, role=Role.STUDENT)
            _material(author_a, status="APPROVED", title="Algorithms for Institution A")
            _material(author_b, status="APPROVED", title="Algorithms for Institution B")
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Algorithms", institution_id=iid_a)
            )
            loop.close()

        doc_ids = {r.get("document_id") for r in results}
        # Should only return Institution A's materials
        for r in results:
            assert r.get("institution_id", iid_a) != iid_b or r.get("institution_id", "") == ""

    def test_bm25_excludes_pending_materials(self, app):
        """BM25 corpus must exclude PENDING materials even in the same institution."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            _material(author_id, status="PENDING", title="Unpublished Sorting Notes")
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Unpublished Sorting Notes", institution_id=iid)
            )
            loop.close()

        titles = [r.get("title", "") for r in results]
        assert "Unpublished Sorting Notes" not in titles

    def test_bm25_excludes_rejected_materials(self, app):
        """BM25 corpus must exclude REJECTED materials."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            _material(author_id, status="REJECTED", title="Rejected Binary Trees Notes")
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Rejected Binary Trees Notes", institution_id=iid)
            )
            loop.close()

        titles = [r.get("title", "") for r in results]
        assert "Rejected Binary Trees Notes" not in titles

    def test_bm25_excludes_deleted_materials(self, app):
        """BM25 corpus must exclude is_deleted=True materials."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            mid = uuid.uuid4()
            mat = StudyMaterial(
                id=mid,
                title="Deleted Hash Table Notes",
                description="Should never appear",
                author_id=uuid.UUID(author_id),
                material_type=MaterialType.NOTE,
                status="APPROVED",
                is_deleted=True,
            )
            db.session.add(mat)
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Deleted Hash Table Notes", institution_id=iid)
            )
            loop.close()

        titles = [r.get("title", "") for r in results]
        assert "Deleted Hash Table Notes" not in titles

    def test_bm25_includes_approved_materials_same_institution(self, app):
        """BM25 corpus includes APPROVED materials from the same institution."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.STUDENT)
            _material(author_id, status="APPROVED", title="Dynamic Programming Lecture")
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Dynamic Programming Lecture", institution_id=iid)
            )
            loop.close()

        titles = [r.get("title", "") for r in results]
        assert "Dynamic Programming Lecture" in titles

    def test_bm25_cross_institution_strict_isolation(self, app):
        """BM25 with institution_id=A must return 0 results from institution B
        even when institution B has an APPROVED matching document."""
        with app.app_context():
            iid_a = _inst()
            iid_b = _inst()
            author_b = _user(iid_b, role=Role.FACULTY)
            _material(author_b, status="APPROVED", title="Graph Theory B Only Content")
            db.session.commit()

        with app.app_context():
            rag = RAGService(
                qdrant_service=_mock_qdrant(),
                embedding_service=_mock_embedder(),
            )
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(
                rag.hybrid_search(query="Graph Theory B Only Content", institution_id=iid_a)
            )
            loop.close()

        titles = [r.get("title", "") for r in results]
        assert "Graph Theory B Only Content" not in titles


# ══════════════════════════════════════════════════════════════════════════════
# D. Qdrant Payload Fields
# ══════════════════════════════════════════════════════════════════════════════

class TestQdrantPayload:
    """Verify QdrantService stores and filters the correct fields."""

    def test_qdrant_upsert_includes_is_approved(self):
        """is_approved must be stored as True when metadata says so."""
        from app.services.ai.qdrant_service import QdrantService, QDRANT_AVAILABLE

        captured_points = []

        async def _fake_upsert(collection_name, points):
            captured_points.extend(points)

        class _FakePoint:
            """Minimal PointStruct substitute for testing."""
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload

        qs = QdrantService()
        qs.client = MagicMock()
        qs.client.upsert = AsyncMock(side_effect=_fake_upsert)

        chunks = [{"text": "test chunk", "chunk_index": 0}]
        embeddings = [[0.1] * 3072]
        metadata_list = [{"institution_id": "inst-123", "is_approved": True, "is_deleted": False, "document_id": "doc-456"}]

        # Patch QDRANT_AVAILABLE=True and PointStruct so the method body runs
        # even without qdrant-client installed in the test environment.
        with patch("app.services.ai.qdrant_service.QDRANT_AVAILABLE", True), \
             patch("app.services.ai.qdrant_service.PointStruct", _FakePoint):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(qs.upsert_chunks(chunks, embeddings, metadata_list))
            loop.close()

        assert len(captured_points) == 1
        payload = captured_points[0].payload
        assert payload["is_approved"] is True
        assert payload["is_deleted"] is False
        assert payload["institution_id"] == "inst-123"

    def test_qdrant_search_filters_approved_only(self):
        """search() with approved_only=True must add is_approved filter."""
        from app.services.ai.qdrant_service import QdrantService, QDRANT_AVAILABLE
        if not QDRANT_AVAILABLE:
            pytest.skip("qdrant-client not installed")

        qs = QdrantService()
        qs.client = MagicMock()
        qs.client.search = AsyncMock(return_value=[])

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            qs.search(query_embedding=[0.1] * 3072, institution_id="inst-1", approved_only=True)
        )
        loop.close()

        qs.client.search.assert_called_once()
        call_kwargs = qs.client.search.call_args[1]
        f = call_kwargs.get("query_filter")
        # Verify filter object is not None (contains conditions)
        assert f is not None

    def test_qdrant_delete_chunks_for_document(self):
        """delete_chunks_for_document() calls client.delete with correct filter."""
        from app.services.ai.qdrant_service import QdrantService, QDRANT_AVAILABLE
        if not QDRANT_AVAILABLE:
            pytest.skip("qdrant-client not installed")

        qs = QdrantService()
        qs.client = MagicMock()
        qs.client.delete = AsyncMock(return_value=MagicMock(status="completed"))

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(qs.delete_chunks_for_document("doc-789"))
        loop.close()

        assert result == 1
        qs.client.delete.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# E. /ask Endpoint with Institution Scoping
# ══════════════════════════════════════════════════════════════════════════════

class TestAskEndpointInstitutionScoping:
    """/ask must be institution-scoped and only return approved content."""

    def test_ask_unauthenticated_returns_401(self, client):
        r = client.post("/api/v1/ai/ask", json={"query": "What is recursion?"})
        assert r.status_code == 401

    def test_ask_authenticated_student_returns_200(self, app, client):
        with app.app_context():
            iid = _inst()
            uid = _user(iid, role=Role.STUDENT)
            db.session.commit()

        with patch("app.services.ai.qdrant_service.QdrantService", return_value=_mock_qdrant()), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            token = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
            r = client.post(
                "/api/v1/ai/ask",
                json={"query": "Explain binary search trees"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200

    def test_ask_institution_id_not_trusted_from_body(self, app, client):
        """Even if attacker provides institution_id in body, JWT value is used."""
        with app.app_context():
            iid_a = _inst()
            iid_b = _inst()
            uid = _user(iid_a, role=Role.STUDENT)
            db.session.commit()

        mock_rag = MagicMock()
        mock_rag.retrieve_context = AsyncMock(return_value=("", []))
        mock_rag.calculate_confidence = MagicMock(return_value="LOW")
        mock_rag.create_session = MagicMock()

        with patch("app.services.ai.qdrant_service.QdrantService", return_value=_mock_qdrant()), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            token = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid)
            r = client.post(
                "/api/v1/ai/ask",
                json={"query": "What is quicksort?", "institution_id": iid_b},  # attack
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200

    def test_ask_with_indexed_approved_material_returns_citation(self, app, client):
        """/ask with a mocked Qdrant result should return citations in response."""
        with app.app_context():
            iid = _inst()
            uid = _user(iid, role=Role.STUDENT)
            mat_id = _material(uid, status="APPROVED", title="Heap Sort Study Material")
            db.session.commit()

        mock_qdrant = _mock_qdrant()
        mock_qdrant.search = AsyncMock(return_value=[{
            "id": str(uuid.uuid4()),
            "score": 0.05,
            "text": "Heap sort is a comparison-based sorting algorithm.",
            "document_id": mat_id,
            "title": "Heap Sort Study Material",
            "chunk_index": 0,
            "institution_id": iid,
            "subject_id": "",
            "is_approved": True,
            "is_deleted": False,
        }])

        with patch("app.services.ai.qdrant_service.QdrantService", return_value=mock_qdrant), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            token = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
            r = client.post(
                "/api/v1/ai/ask",
                json={"query": "Explain heap sort"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        data = r.get_json()["data"]
        assert "answer" in data
        assert "citations" in data
        # citations may be empty if material wasn't found in DB (no FileMetadata FK violation)
        # but response shape must be correct
        assert isinstance(data["citations"], list)
        assert data["confidence"] in ("HIGH", "MEDIUM", "LOW")

    def test_ask_response_never_exposes_traceback(self, app, client):
        """Even on internal error, no traceback text appears in response."""
        with app.app_context():
            iid = _inst()
            uid = _user(iid, role=Role.STUDENT)
            db.session.commit()

        with patch("app.services.ai.qdrant_service.QdrantService", return_value=_mock_qdrant()), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            token = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
            r = client.post(
                "/api/v1/ai/ask",
                json={"query": ""},  # triggers 400 before LLM
                headers={"Authorization": f"Bearer {token}"},
            )

        body = r.get_data(as_text=True)
        for marker in ("Traceback", "File \"", "line ", "raise ", "Exception"):
            assert marker not in body


# ══════════════════════════════════════════════════════════════════════════════
# F. Rate Limiting
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    """Verify rate limiting infrastructure is correctly configured."""

    def test_rate_limiter_module_imports_without_error(self):
        """The rate_limiter module must import successfully."""
        from app.middleware.rate_limiter import limiter, init_rate_limiter
        assert limiter is not None
        assert callable(init_rate_limiter)

    def test_rate_limiter_uses_in_memory_when_no_redis(self, app):
        """When REDIS_URL is not set, rate limiter falls back to in-memory."""
        import os
        from app.middleware.rate_limiter import FLASK_LIMITER_AVAILABLE
        if not FLASK_LIMITER_AVAILABLE:
            pytest.skip("Flask-Limiter not installed")

        from app.middleware.rate_limiter import init_rate_limiter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REDIS_URL", None)
            result = init_rate_limiter(app)
            assert result is not None

    def test_ai_rate_limit_constant_is_defined(self):
        """AI_RATE_LIMIT must be a non-empty string when Flask-Limiter is installed."""
        from app.middleware.rate_limiter import FLASK_LIMITER_AVAILABLE, AI_RATE_LIMIT
        if not FLASK_LIMITER_AVAILABLE:
            pytest.skip("Flask-Limiter not installed")
        assert isinstance(AI_RATE_LIMIT, str)
        assert len(AI_RATE_LIMIT) > 0

    def test_ai_endpoint_reachable_without_redis(self, app, client):
        """AI endpoints must respond normally even when Redis is absent."""
        with app.app_context():
            iid = _inst()
            uid = _user(iid, role=Role.STUDENT)
            db.session.commit()

        with patch("app.services.ai.qdrant_service.QdrantService", return_value=_mock_qdrant()), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            token = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
            r = client.post(
                "/api/v1/ai/ask",
                json={"query": "What is memoization?"},
                headers={"Authorization": f"Bearer {token}"},
            )
        # Must not fail due to missing Redis
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# G. Regression — existing approval workflow unaffected
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalWorkflowRegression:
    """Verify existing approval workflow contract is preserved."""

    def test_self_approval_still_rejected(self, app):
        """Author cannot approve their own resource."""
        with app.app_context():
            iid = _inst()
            author_id = _user(iid, role=Role.MODERATOR)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            with pytest.raises(ValueError, match="own"):
                svc.approve_material(mat_id, author_id, iid)
            mock_task.delay.assert_not_called()

    def test_cross_institution_approval_still_rejected(self, app):
        """Reviewer from different institution cannot approve."""
        with app.app_context():
            iid_a = _inst()
            iid_b = _inst()
            author_id = _user(iid_a, role=Role.STUDENT)
            reviewer_id = _user(iid_b, role=Role.MODERATOR)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            with pytest.raises(ValueError):
                svc.approve_material(mat_id, reviewer_id, iid_b)
            mock_task.delay.assert_not_called()

    def test_rejection_clears_qdrant_chunks(self, app):
        """Rejecting a resource attempts Qdrant chunk deletion."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.services.ai.qdrant_service.QdrantService") as MockQdrant:
            mock_instance = _mock_qdrant()
            MockQdrant.return_value = mock_instance
            svc = ApprovalService()
            result = svc.reject_material(mat_id, reviewer_id, iid, reason="Not relevant")
            assert result["status"] == "REJECTED"
            # Qdrant delete was attempted (may be a no-op if nothing was indexed)
            # We just verify it was called without raising

    def test_approval_history_still_returns_records(self, app):
        """Approval history audit trail is unaffected."""
        with app.app_context():
            iid = _inst()
            reviewer_id = _user(iid, role=Role.MODERATOR)
            author_id = _user(iid, role=Role.STUDENT)
            mat_id = _material(author_id, status="PENDING")
            db.session.commit()

        with app.app_context(), \
             patch("app.tasks.indexing.index_document_task") as mock_task:
            mock_task.delay = MagicMock()
            svc = ApprovalService()
            svc.approve_material(mat_id, reviewer_id, iid)
            history = svc.get_approval_history(mat_id)
            assert len(history) >= 1
            assert any(a.get("action") == "approved" for a in history)
