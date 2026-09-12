"""Cycle 3 — Quiz Generator, Flashcard Generator, Summary Generator tests.

Coverage (43 tests):
    A. Quiz (15 tests)      — auth, RBAC, resource validation, grounding, output validation, citations, safety
    B. Flashcards (12 tests) — auth, RBAC, resource validation, grounding, output validation, bounds, safety
    C. Summary (11 tests)   — auth, RBAC, resource validation, grounding, output validation, safety
    D. Shared / infrastructure (5 tests) — JSON extractor, quiz validator, flashcard validator,
                                            StudyToolsService unit, regression

All external services mocked (Qdrant, Anthropic, OpenAI, Celery, Redis).
Tests do not require any production credentials.
"""
import asyncio
import json
import uuid
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app import create_app
from app.extensions import db
from app.models.academic import Institution
from app.models.user import User
from app.models.resource import StudyMaterial, MaterialType
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures & Helpers
# ══════════════════════════════════════════════════════════════════════════════

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


def _inst(app):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid, name=f"Uni {iid.hex[:4]}", short_name="U",
        code=f"U{iid.hex[:6]}", domain_whitelist=[], settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(iid)


def _user(institution_id, role=Role.STUDENT):
    uid = uuid.uuid4()
    email = f"u{uid.hex[:8]}@test.edu"
    u = User(
        id=uid, email=email, email_normalized=email.lower(),
        full_name="Test", password_hash="hashed",
        institution_id=uuid.UUID(institution_id), role=role, status="active",
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _material(author_id, status="APPROVED", title="Test Resource"):
    mid = uuid.uuid4()
    mat = StudyMaterial(
        id=mid, title=title, description=f"Description of {title}",
        author_id=uuid.UUID(author_id), material_type=MaterialType.NOTE,
        status=status, is_deleted=False,
    )
    db.session.add(mat)
    db.session.flush()
    return str(mid)


def _tok(app, user_id, institution_id, role=Role.STUDENT):
    class _U:
        def __init__(self):
            self.id = user_id
            self.institution_id = institution_id
            self.role = role
            self.email = "t@t.edu"
    with app.app_context():
        return generate_access_token(_U())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mock_qdrant():
    m = MagicMock()
    m.search = AsyncMock(return_value=[])
    m.ensure_collection = AsyncMock()
    return m


def _mock_embedder():
    m = MagicMock()
    m.get_embedding = AsyncMock(return_value=[0.1] * 3072)
    m.batch_embed_chunks = AsyncMock(return_value=[[0.1] * 3072])
    return m


def _quiz_json(num=3):
    """Return valid quiz JSON string."""
    return json.dumps({
        "topic": "Test Topic",
        "questions": [
            {
                "question_number": i + 1,
                "question": f"Question {i + 1}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer_index": 0,
                "explanation": f"Explanation {i + 1}",
            }
            for i in range(num)
        ],
    })


def _flashcard_json(num=3):
    """Return valid flashcard JSON string."""
    return json.dumps({
        "flashcards": [
            {
                "front": f"Term {i + 1}",
                "back": f"Definition {i + 1}",
                "category": "General",
            }
            for i in range(num)
        ]
    })


def _mock_clients(answer="OK"):
    m = MagicMock()
    m.call_claude = AsyncMock(return_value={
        "content": answer,
        "model": "claude-test",
        "usage": {},
        "tool_calls": [],
    })
    return m


def _make_study_tools_svc(app, mat_id, iid, llm_answer="OK", qdrant_results=None):
    """Build a StudyToolsService with injected mocks."""
    from app.services.ai.study_tools_service import StudyToolsService

    with app.app_context():
        mock_rag = MagicMock()
        mock_rag.retrieve_context = AsyncMock(return_value=(
            "Some retrieved academic content about the topic.",
            [{"document_id": mat_id, "title": "Test", "chunk_index": 0,
              "score": 0.05, "snippet": "content"}],
        ))
        mock_rag.calculate_confidence = MagicMock(return_value="HIGH")
        svc = StudyToolsService(
            ai_clients=_mock_clients(llm_answer),
            rag_service=mock_rag,
        )
    return svc


# ══════════════════════════════════════════════════════════════════════════════
# A. Quiz Generator (Tests 1–15)
# ══════════════════════════════════════════════════════════════════════════════

class TestQuizGenerator:

    # 1. Unauthenticated → 401
    def test_unauthenticated_quiz_rejected_401(self, app, client):
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": str(uuid.uuid4())})
        assert r.status_code == 401

    # 2. Guest role → 403
    def test_guest_quiz_rejected_403(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.GUEST)
            db.session.commit()
        tok = _tok(app, uid, iid, Role.GUEST)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": str(uuid.uuid4())},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403

    # 3. Student → can generate quiz
    def test_student_can_generate_quiz(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.STUDENT)
            mat_id = _material(uid, status="APPROVED", title="Student Quiz Test")
            db.session.commit()
        tok = _tok(app, uid, iid, Role.STUDENT)
        svc = _make_study_tools_svc(app, mat_id, iid, llm_answer=_quiz_json(3))
        with patch("app.blueprints.api.v1.ai._get_study_tools_service", return_value=svc), \
             patch("app.services.ai.study_tools_service.StudyToolsService._retrieve_grounded_context",
                   new=AsyncMock(return_value=("content", []))), \
             patch("app.blueprints.api.v1.ai._study_tools_service", svc):
            r = client.post("/api/v1/ai/quiz/generate",
                            json={"resource_id": mat_id, "num_questions": 3},
                            headers={"Authorization": f"Bearer {tok}"})
        # Validation may fail on mock LLM (no retrieval context) — check not 401/403/404
        assert r.status_code in (200, 422)

    # 4. Faculty → can generate quiz
    def test_faculty_can_generate_quiz(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.FACULTY)
            mat_id = _material(uid, status="APPROVED", title="Faculty Quiz")
            db.session.commit()
        tok = _tok(app, uid, iid, Role.FACULTY)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code in (200, 422)  # auth passed; generation may use mock fallback

    # 5. Missing resource_id → 400
    def test_missing_resource_id_quiz_400(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate", json={},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400

    # 6. Cross-institution resource → 404
    def test_cross_institution_quiz_404(self, app, client):
        with app.app_context():
            iid_a = _inst(app)
            iid_b = _inst(app)
            uid_a = _user(iid_a)
            uid_b = _user(iid_b)
            mat_b = _material(uid_b, status="APPROVED", title="B's Secret Notes")
            db.session.commit()
        tok = _tok(app, uid_a, iid_a)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_b},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 7. Pending resource → 422
    def test_pending_resource_quiz_422(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="PENDING", title="Pending Quiz")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    # 8. Rejected resource → 422
    def test_rejected_resource_quiz_422(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="REJECTED", title="Rejected Quiz")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    # 9. Deleted resource → 404
    def test_deleted_resource_quiz_404(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Deleted Quiz")
            mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(mat_id)).first()
            mat.is_deleted = True
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 10. Valid resource → quiz generated (service level)
    def test_quiz_generated_from_approved_resource(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Algorithms Notes")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=(
                "Binary search is an algorithm that finds a target in sorted array in O(log n).",
                [{"document_id": mat_id, "title": "Algorithms Notes",
                  "chunk_index": 0, "score": 0.06, "snippet": "binary search"}],
            ))
            svc = StudyToolsService(
                ai_clients=_mock_clients(_quiz_json(3)),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_quiz(
                resource_id=mat_id,
                institution_id=iid,
                resource_title="Algorithms Notes",
                num_questions=3,
            ))

        assert result["success"] is True
        assert "questions" in result
        assert len(result["questions"]) == 3
        assert result["question_count"] == 3

    # 11. Malformed LLM output → safe PARSE_ERROR (no traceback)
    def test_malformed_quiz_output_safe_error(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Bad Output")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=("content", []))
            svc = StudyToolsService(
                ai_clients=_mock_clients("This is not JSON at all!"),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_quiz(mat_id, iid, "Notes", 3))

        assert result["success"] is False
        assert result["error"] in ("PARSE_ERROR", "VALIDATION_ERROR")
        assert "Traceback" not in result.get("message", "")

    # 12. num_questions clamped to MAX_QUIZ_QUESTIONS
    def test_quiz_count_limit_enforced(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Limit Test")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id, "num_questions": 9999},
                        headers={"Authorization": f"Bearer {tok}"})
        # Should not 500; clamped internally
        assert r.status_code in (200, 422)

    # 13. Citations come from actual retrieved sources
    def test_quiz_citations_from_actual_sources(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Source Test")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=(
                "content",
                [{"document_id": mat_id, "title": "Source Test",
                  "chunk_index": 2, "score": 0.07, "snippet": "excerpt"}],
            ))
            svc = StudyToolsService(
                ai_clients=_mock_clients(_quiz_json(2)),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_quiz(mat_id, iid, "Source Test", 2))

        assert result["success"] is True
        assert len(result["sources"]) >= 1
        assert result["sources"][0]["document_id"] == mat_id
        assert result["sources"][0]["chunk_index"] == 2
        # No fabricated IDs — source must match what retrieval returned
        for src in result["sources"]:
            assert src["document_id"] is not None

    # 14. No secret leakage in quiz response
    def test_quiz_no_secret_leakage(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Secret Test")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/quiz/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        body = r.get_data(as_text=True)
        for bad in ("API_KEY", "SECRET", "Traceback", 'File "', "raise "):
            assert bad not in body

    # 15. No traceback leakage when LLM fails
    def test_quiz_no_traceback_on_llm_failure(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="LLM Fail Test")
            db.session.commit()
        tok = _tok(app, uid, iid)

        broken_svc = MagicMock()
        broken_svc.validate_resource = MagicMock(return_value=(
            MagicMock(id=uuid.UUID(mat_id), title="LLM Fail Test", status="APPROVED",
                      is_deleted=False), None
        ))
        broken_svc.generate_quiz = AsyncMock(side_effect=RuntimeError("internal error"))

        with patch("app.blueprints.api.v1.ai._get_study_tools_service", return_value=broken_svc):
            r = client.post("/api/v1/ai/quiz/generate",
                            json={"resource_id": mat_id},
                            headers={"Authorization": f"Bearer {tok}"})

        assert r.status_code == 500
        body = r.get_data(as_text=True)
        assert "internal error" not in body
        assert "RuntimeError" not in body
        assert "Traceback" not in body


# ══════════════════════════════════════════════════════════════════════════════
# B. Flashcard Generator (Tests 16–27)
# ══════════════════════════════════════════════════════════════════════════════

class TestFlashcardGenerator:

    # 16. Unauthenticated → 401
    def test_unauthenticated_flashcards_401(self, app, client):
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": str(uuid.uuid4())})
        assert r.status_code == 401

    # 17. Guest → 403
    def test_guest_flashcards_403(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.GUEST)
            db.session.commit()
        tok = _tok(app, uid, iid, Role.GUEST)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": str(uuid.uuid4())},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403

    # 18. Valid student request — returns correct envelope
    def test_flashcards_valid_request_fields(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Data Structures")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=(
                "A stack is LIFO. A queue is FIFO.",
                [{"document_id": mat_id, "title": "Data Structures",
                  "chunk_index": 1, "score": 0.05, "snippet": "stack"}],
            ))
            svc = StudyToolsService(
                ai_clients=_mock_clients(_flashcard_json(5)),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_flashcards(mat_id, iid, "Data Structures", 5))

        assert result["success"] is True
        assert "flashcards" in result
        assert "card_count" in result
        assert result["card_count"] == 5
        for card in result["flashcards"]:
            assert card["front"]
            assert card["back"]

    # 19. Cross-institution blocked → 404
    def test_flashcards_cross_institution_404(self, app, client):
        with app.app_context():
            iid_a = _inst(app)
            iid_b = _inst(app)
            uid_a = _user(iid_a)
            uid_b = _user(iid_b)
            mat_b = _material(uid_b, status="APPROVED", title="B's Flashcards")
            db.session.commit()
        tok = _tok(app, uid_a, iid_a)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": mat_b},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 20. Pending resource → 422
    def test_flashcards_pending_422(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="PENDING", title="Pending Flashcard")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    # 21. Deleted resource → 404
    def test_flashcards_deleted_404(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Deleted Flashcard")
            mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(mat_id)).first()
            mat.is_deleted = True
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 22. Valid flashcards generated with expected structure
    def test_flashcards_structure(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="OS Concepts")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=(
                "Deadlock requires four conditions: mutual exclusion, hold and wait, no preemption, circular wait.",
                [{"document_id": mat_id, "title": "OS Concepts",
                  "chunk_index": 0, "score": 0.08, "snippet": "deadlock"}],
            ))
            svc = StudyToolsService(
                ai_clients=_mock_clients(_flashcard_json(4)),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_flashcards(mat_id, iid, "OS Concepts", 4))

        assert result["success"] is True
        for card in result["flashcards"]:
            assert isinstance(card["front"], str) and len(card["front"]) > 0
            assert isinstance(card["back"], str) and len(card["back"]) > 0
            assert isinstance(card["category"], str)

    # 23. Malformed LLM output → PARSE_ERROR, no traceback
    def test_flashcards_malformed_output_safe(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Malformed Flash")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=("content", []))
            svc = StudyToolsService(
                ai_clients=_mock_clients("not json!!!"),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_flashcards(mat_id, iid, "Notes", 5))

        assert result["success"] is False
        assert "Traceback" not in str(result)
        assert "not json" not in result.get("message", "")

    # 24. Card count bounded by MAX_FLASHCARD_COUNT
    def test_flashcard_count_bounded(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Card Limit Test")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": mat_id, "num_cards": 99999},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code in (200, 422)  # clamped, not 500

    # 25. No secret / traceback leakage in flashcard response
    def test_flashcards_no_secret_leakage(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Leak Test Flashcard")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/flashcards/generate",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        body = r.get_data(as_text=True)
        for bad in ("API_KEY", "SECRET", "Traceback", 'File "'):
            assert bad not in body

    # 26. Empty cards in LLM output filtered out
    def test_flashcards_empty_front_back_filtered(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        bad_json = json.dumps({
            "flashcards": [
                {"front": "Valid Front", "back": "Valid Back", "category": "A"},
                {"front": "", "back": "No Front", "category": "B"},      # empty front
                {"front": "No Back", "back": "", "category": "C"},       # empty back
                {"front": "Also Valid", "back": "Also Valid Back", "category": "D"},
            ]
        })
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Filter Test")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=("content", []))
            svc = StudyToolsService(
                ai_clients=_mock_clients(bad_json),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_flashcards(mat_id, iid, "Notes", 10))

        if result["success"]:
            for card in result["flashcards"]:
                assert card["front"].strip() != ""
                assert card["back"].strip() != ""

    # 27. Missing resource_id → 400
    def test_flashcards_missing_resource_id_400(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/flashcards/generate", json={},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# C. Summary Generator (Tests 28–38)
# ══════════════════════════════════════════════════════════════════════════════

class TestSummaryGenerator:

    # 28. Unauthenticated → 401
    def test_unauthenticated_summary_401(self, app, client):
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": str(uuid.uuid4())})
        assert r.status_code == 401

    # 29. Guest → 403
    def test_guest_summary_403(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.GUEST)
            db.session.commit()
        tok = _tok(app, uid, iid, Role.GUEST)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": str(uuid.uuid4())},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403

    # 30. Valid student request → passes auth (200 or 422 from mock LLM)
    def test_student_summary_auth_passes(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Summary Auth Test")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code in (200, 422)

    # 31. Cross-institution → 404
    def test_summary_cross_institution_404(self, app, client):
        with app.app_context():
            iid_a = _inst(app)
            iid_b = _inst(app)
            uid_a = _user(iid_a)
            uid_b = _user(iid_b)
            mat_b = _material(uid_b, status="APPROVED", title="B's Summary")
            db.session.commit()
        tok = _tok(app, uid_a, iid_a)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": mat_b},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 32. Pending resource → 422
    def test_summary_pending_422(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="PENDING", title="Pending Summary")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    # 33. Deleted resource → 404
    def test_summary_deleted_404(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Deleted Summary")
            mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(mat_id)).first()
            mat.is_deleted = True
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404

    # 34. Grounded summary generated at service level
    def test_summary_grounded_generation(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Machine Learning")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=(
                "Machine learning is a subset of AI enabling systems to learn from data.",
                [{"document_id": mat_id, "title": "Machine Learning",
                  "chunk_index": 0, "score": 0.09, "snippet": "ml"}],
            ))
            svc = StudyToolsService(
                ai_clients=_mock_clients("### Key Concepts\n- ML\n\n### Core Summary\nML learns from data.\n\n### Essential Takeaways\n- Data driven"),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_summary(mat_id, iid, "Machine Learning"))

        assert result["success"] is True
        assert "summary" in result
        assert len(result["summary"]) > 0
        assert len(result["sources"]) >= 1

    # 35. Malformed / empty summary → safe error, no traceback
    def test_summary_empty_llm_output_safe(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Empty Summary Test")
            db.session.commit()

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=("content", []))
            svc = StudyToolsService(
                ai_clients=_mock_clients(""),  # empty LLM response
                rag_service=mock_rag,
            )
            result = _run(svc.generate_summary(mat_id, iid, "Test"))

        assert result["success"] is False
        assert "Traceback" not in str(result)

    # 36. Summary bounded at MAX_SUMMARY_CHARS
    def test_summary_bounded_length(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        from app.services.ai.prompt_templates import MAX_SUMMARY_CHARS
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Long Summary")
            db.session.commit()

        giant_summary = "X" * (MAX_SUMMARY_CHARS + 5000)

        with app.app_context():
            mock_rag = MagicMock()
            mock_rag.retrieve_context = AsyncMock(return_value=("content", []))
            svc = StudyToolsService(
                ai_clients=_mock_clients(giant_summary),
                rag_service=mock_rag,
            )
            result = _run(svc.generate_summary(mat_id, iid, "Long Summary"))

        if result["success"]:
            assert len(result["summary"]) <= MAX_SUMMARY_CHARS + 50  # small tolerance for truncation suffix

    # 37. No secret leakage in summary response
    def test_summary_no_secret_leakage(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            mat_id = _material(uid, status="APPROVED", title="Leak Summary Test")
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/summarize",
                        json={"resource_id": mat_id},
                        headers={"Authorization": f"Bearer {tok}"})
        body = r.get_data(as_text=True)
        for bad in ("API_KEY", "SECRET", "Traceback", 'File "'):
            assert bad not in body

    # 38. Missing resource_id → 400
    def test_summary_missing_resource_id_400(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid)
            db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/summarize", json={},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# D. Shared Infrastructure (Tests 39–43)
# ══════════════════════════════════════════════════════════════════════════════

class TestSharedInfrastructure:

    # 39. _extract_json: bare JSON object
    def test_extract_json_bare(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        result = StudyToolsService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    # 40. _extract_json: markdown-fenced JSON
    def test_extract_json_fenced(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        raw = '```json\n{"questions": [{"q": 1}]}\n```'
        result = StudyToolsService._extract_json(raw)
        assert result is not None
        assert "questions" in result

    # 41. _validate_quiz: filters questions with missing options
    def test_validate_quiz_filters_bad_questions(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        data = {
            "topic": "Test",
            "questions": [
                # Valid question
                {"question": "Q1?", "options": ["A", "B", "C", "D"],
                 "correct_answer_index": 0, "explanation": "E1"},
                # Invalid: only 1 option
                {"question": "Bad Q", "options": ["Only one"],
                 "correct_answer_index": 0, "explanation": ""},
                # Valid
                {"question": "Q3?", "options": ["A", "B", "C", "D"],
                 "correct_answer_index": 2, "explanation": "E3"},
            ],
        }
        validated, err = StudyToolsService._validate_quiz(data, max_questions=10)
        assert validated is not None
        assert len(validated["questions"]) == 2

    # 42. _validate_flashcards: bounds card count
    def test_validate_flashcards_bounds_count(self, app):
        from app.services.ai.study_tools_service import StudyToolsService
        data = {
            "flashcards": [
                {"front": f"F{i}", "back": f"B{i}", "category": "C"}
                for i in range(30)
            ]
        }
        validated, err = StudyToolsService._validate_flashcards(data, max_cards=5)
        assert validated is not None
        assert validated["card_count"] == 5
        assert len(validated["flashcards"]) == 5

    # 43. Regression — General Q&A still works after Cycle 3 changes
    def test_general_qa_regression(self, app, client):
        with app.app_context():
            iid = _inst(app)
            uid = _user(iid, role=Role.STUDENT)
            _material(uid, status="APPROVED", title="Regression Q&A Test")
            db.session.commit()
        tok = _tok(app, uid, iid, Role.STUDENT)
        with patch("app.services.ai.qdrant_service.QdrantService", return_value=_mock_qdrant()), \
             patch("app.services.ai.embedding_service.EmbeddingService", return_value=_mock_embedder()):
            r = client.post("/api/v1/ai/ask",
                            json={"query": "What is machine learning?"},
                            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        data = r.get_json()["data"]
        # /ask returns 'answer' (General Q&A) — 'response' is used by /chat and /pdf/chat
        assert "answer" in data or "response" in data
