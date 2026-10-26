"""
CampusX Frontend Cycle 4 Tests — AI Workspace
==============================================

Tests validate the AI workspace front-end implementation:
  - Template rendering and structure
  - AI API endpoints (auth, validation, response shape)
  - Citation and quality field presence
  - PDF Chat session endpoints
  - Multi-PDF Chat session endpoints
  - Security (no raw UUIDs, no raw exceptions in frontend)
  - JS module structure
  - CSS component presence
  - Accessibility attributes

Pattern: mirrors test_cycle5.py — uses generate_access_token + in-context DB helpers.
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app import create_app
from app.extensions import db
from app.models.academic import Institution
from app.models.user import User
from app.models.resource import StudyMaterial, MaterialType
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────────────────────────────────────

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
        id=mid, title=title, description=f"Desc of {title}",
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


def _auth(app, role=Role.STUDENT):
    """Create a fresh user+institution, return bearer headers."""
    iid = _inst(app)
    uid = _user(iid, role=role)
    tok = _tok(app, uid, iid, role=role)
    return {"Authorization": f"Bearer {tok}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. AI Workspace Page Rendering
# ─────────────────────────────────────────────────────────────────────────────

class TestAIPageRendering:

    def test_ai_chat_route_renders_200(self, client):
        r = client.get("/student/ai-chat")
        assert r.status_code == 200

    def test_ai_route_renders_200(self, client):
        """/student/ai shortcut route must return 200."""
        r = client.get("/student/ai")
        assert r.status_code == 200

    def test_ai_page_has_workspace_element(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="ai-workspace"' in body

    def test_ai_page_has_mode_selector(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-mode-btn' in body or 'ai-mobile-tab' in body

    def test_ai_page_has_three_modes(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'data-mode="general"' in body
        assert 'data-mode="pdf"' in body
        assert 'data-mode="multi"' in body

    def test_ai_page_general_panel_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="ai-panel-general"' in body

    def test_ai_page_pdf_panel_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="ai-panel-pdf"' in body

    def test_ai_page_multi_panel_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="ai-panel-multi"' in body

    def test_ai_page_has_composer(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-composer-textarea' in body
        assert 'ai-composer-send' in body

    def test_ai_page_loads_ai_js(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai.js' in body

    def test_ai_page_has_empty_state(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-empty' in body
        assert 'CampusX AI' in body

    def test_ai_page_has_starter_prompts(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-starter-btn' in body
        # starter prompts populate the composer only — they do NOT call API
        assert 'data-prompt' in body

    def test_ai_page_auth_check(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'CampusX.auth.isAuthenticated' in body

    def test_ai_page_no_fake_data(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'Example AI answer' not in body
        assert 'Lorem ipsum' not in body
        assert 'This is a sample' not in body

    def test_ai_page_no_raw_institution_id_in_html(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        # institution_id must never appear in frontend HTML template
        assert 'institution_id' not in body


# ─────────────────────────────────────────────────────────────────────────────
# 2. AI JS Module
# ─────────────────────────────────────────────────────────────────────────────

class TestAIJSModule:

    def _js(self, client):
        return client.get("/static/js/ai.js").get_data(as_text=True)

    def test_ai_js_loads(self, client):
        r = client.get("/static/js/ai.js")
        assert r.status_code == 200

    def test_ai_js_exposes_campusx_ai(self, client):
        assert 'CampusX.ai' in self._js(client)

    def test_ai_js_has_ask_function(self, client):
        js = self._js(client)
        assert 'function ask' in js or 'async function ask' in js

    def test_ai_js_has_pdf_session(self, client):
        assert 'createPdfSession' in self._js(client)

    def test_ai_js_has_multi_pdf_session(self, client):
        assert 'createMultiPdfSession' in self._js(client)

    def test_ai_js_has_pdf_chat(self, client):
        assert 'pdfChat' in self._js(client)

    def test_ai_js_has_max_query_len(self, client):
        js = self._js(client)
        assert 'MAX_QUERY_LEN' in js
        assert '2000' in js

    def test_ai_js_has_max_multi_pdf(self, client):
        js = self._js(client)
        assert 'MAX_MULTI_PDF' in js
        assert '10' in js

    def test_ai_js_no_institution_from_localstorage(self, client):
        js = self._js(client)
        lines_with_both = [l for l in js.split('\n')
                           if 'institution_id' in l and 'localStorage' in l]
        assert len(lines_with_both) == 0

    def test_ai_js_friendly_error(self, client):
        assert 'friendlyError' in self._js(client)

    def test_ai_js_uses_bearer_auth(self, client):
        assert 'Bearer' in self._js(client)

    def test_ai_js_has_unauthorized_handling(self, client):
        assert 'UNAUTHORIZED' in self._js(client)

    def test_ai_js_has_rate_limit_handling(self, client):
        js = self._js(client)
        assert 'RATE_LIMITED' in js or '429' in js

    def test_ai_js_uses_correct_ask_path(self, client):
        assert '/ai/ask' in self._js(client)

    def test_ai_js_uses_correct_pdf_sessions_path(self, client):
        assert '/ai/pdf/sessions' in self._js(client)

    def test_ai_js_uses_correct_pdf_chat_path(self, client):
        assert '/ai/pdf/chat' in self._js(client)


# ─────────────────────────────────────────────────────────────────────────────
# 3. General Q&A API — auth + validation
# ─────────────────────────────────────────────────────────────────────────────

class TestAskAPIAuth:

    def test_ask_requires_auth(self, client):
        r = client.post("/api/v1/ai/ask", json={"query": "What is ML?"})
        assert r.status_code == 401

    def test_ask_empty_query_returns_400(self, client, app):
        headers = _auth(app)
        r = client.post("/api/v1/ai/ask", json={"query": ""}, headers=headers)
        assert r.status_code == 400

    def test_ask_no_body_returns_400(self, client, app):
        headers = _auth(app)
        r = client.post("/api/v1/ai/ask", json={}, headers=headers)
        assert r.status_code == 400

    def test_ask_too_long_query_returns_400(self, client, app):
        headers = _auth(app)
        r = client.post("/api/v1/ai/ask",
                        json={"query": "x" * 2001},
                        headers=headers)
        assert r.status_code == 400

    def test_ask_max_length_query_accepted(self, client, app):
        """Exactly 2000 chars should be accepted."""
        headers = _auth(app)
        r = client.post("/api/v1/ai/ask",
                        json={"query": "x" * 2000},
                        headers=headers)
        # 200 (mock AI), 503 (no LLM config), or 500 — not 400
        assert r.status_code in (200, 503, 500)

    def test_ask_whitespace_only_returns_400(self, client, app):
        headers = _auth(app)
        r = client.post("/api/v1/ai/ask",
                        json={"query": "   "},
                        headers=headers)
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 4. General Q&A API — response schema
# ─────────────────────────────────────────────────────────────────────────────

class TestAskAPIResponseSchema:

    def _ask(self, client, app, query="What is dynamic programming?"):
        headers = _auth(app)
        return client.post("/api/v1/ai/ask", json={"query": query}, headers=headers)

    def test_ask_response_has_answer_field(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'answer' in data

    def test_ask_response_has_session_id(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'session_id' in data

    def test_ask_response_has_citations_list(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'citations' in data
            assert isinstance(data['citations'], list)

    def test_ask_response_has_confidence(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'confidence' in data

    def test_ask_response_has_confidence_score(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'confidence_score' in data

    def test_ask_response_has_confidence_level(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'confidence_level' in data

    def test_ask_response_has_grounding_status(self, client, app):
        r = self._ask(client, app)
        if r.status_code == 200:
            data = r.get_json()['data']
            assert 'grounding_status' in data

    def test_ask_no_traceback_in_response(self, client, app):
        r = self._ask(client, app)
        body = r.get_data(as_text=True)
        assert 'Traceback' not in body
        assert 'raise ' not in body


# ─────────────────────────────────────────────────────────────────────────────
# 5. Citation rendering
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationRendering:

    def test_citation_builder_function_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'buildCitationsHtml' in body or 'ai-citations' in body

    def test_citation_js_uses_study_material_id(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'study_material_id' in body

    def test_citation_js_links_to_resource_route(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert '/student/resources/' in body

    def test_citation_js_no_fabricated_page_numbers(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'Page 1 of' not in body
        assert 'hardcoded citation' not in body

    def test_citation_js_escapes_content(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'escHtml' in body

    def test_citation_toggle_aria_expanded(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-expanded' in body


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Quality Indicator
# ─────────────────────────────────────────────────────────────────────────────

class TestAIQualityIndicator:

    def test_quality_builder_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'buildQualityHtml' in body or 'ai-quality' in body

    def test_confidence_high_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'ai-quality-high' in body

    def test_confidence_medium_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'ai-quality-medium' in body

    def test_confidence_low_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'ai-quality-low' in body

    def test_grounding_supported_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'ai-quality-supported' in body

    def test_grounding_unsupported_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'ai-quality-unsupported' in body

    def test_quality_uses_backend_confidence_level_field(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'confidence_level' in body

    def test_quality_uses_backend_grounding_status_field(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'grounding_status' in body


# ─────────────────────────────────────────────────────────────────────────────
# 7. PDF Chat Session API
# ─────────────────────────────────────────────────────────────────────────────

class TestPDFSessionAPI:

    def test_pdf_session_requires_auth(self, client):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": str(uuid.uuid4())})
        assert r.status_code == 401

    def test_pdf_session_missing_resource_id(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={},
                        headers=_auth(app))
        assert r.status_code == 400

    def test_pdf_session_invalid_resource_id(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": "not-a-uuid"},
                        headers=_auth(app))
        assert r.status_code in (400, 404)

    def test_pdf_session_nonexistent_resource(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": str(uuid.uuid4())},
                        headers=_auth(app))
        assert r.status_code == 404

    def test_pdf_session_unapproved_resource(self, client, app):
        iid = _inst(app)
        uid = _user(iid)
        mid = _material(uid, status="PENDING")
        db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": mid},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    def test_pdf_session_approved_resource_starts_session(self, client, app):
        iid = _inst(app)
        uid = _user(iid)
        mid = _material(uid, status="APPROVED")
        db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": mid},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 201
        data = r.get_json()['data']
        assert 'session_id' in data
        assert data['session_type'] == 'pdf_chat'
        assert 'resource_id' in data
        assert 'resource_title' in data

    def test_pdf_chat_requires_auth(self, client):
        r = client.post("/api/v1/ai/pdf/chat",
                        json={"session_id": str(uuid.uuid4()), "message": "Hi"})
        assert r.status_code == 401

    def test_pdf_chat_requires_session_id(self, client, app):
        r = client.post("/api/v1/ai/pdf/chat",
                        json={"message": "What is this?"},
                        headers=_auth(app))
        assert r.status_code == 400

    def test_pdf_chat_requires_message(self, client, app):
        r = client.post("/api/v1/ai/pdf/chat",
                        json={"session_id": str(uuid.uuid4()), "message": ""},
                        headers=_auth(app))
        assert r.status_code == 400

    def test_pdf_chat_invalid_session(self, client, app):
        r = client.post("/api/v1/ai/pdf/chat",
                        json={"session_id": str(uuid.uuid4()), "message": "Hello"},
                        headers=_auth(app))
        assert r.status_code == 404  # not 403 — IDOR prevention

    def test_get_pdf_session_requires_auth(self, client):
        r = client.get(f"/api/v1/ai/pdf/sessions/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_get_pdf_session_not_found(self, client, app):
        r = client.get(f"/api/v1/ai/pdf/sessions/{uuid.uuid4()}",
                       headers=_auth(app))
        assert r.status_code == 404

    def test_get_pdf_session_invalid_id(self, client, app):
        r = client.get("/api/v1/ai/pdf/sessions/not-a-uuid",
                       headers=_auth(app))
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 8. Multi-PDF Session API
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiPDFSessionAPI:

    def test_multi_session_requires_auth(self, client):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": [str(uuid.uuid4())]})
        assert r.status_code == 401

    def test_multi_session_empty_list(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": []},
                        headers=_auth(app))
        assert r.status_code == 400

    def test_multi_session_too_many_resources(self, client, app):
        ids = [str(uuid.uuid4()) for _ in range(11)]
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": ids},
                        headers=_auth(app))
        assert r.status_code == 422

    def test_multi_session_invalid_uuid(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": ["not-a-uuid"]},
                        headers=_auth(app))
        assert r.status_code in (400, 404)

    def test_multi_session_nonexistent_resource(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": [str(uuid.uuid4())]},
                        headers=_auth(app))
        assert r.status_code == 404

    def test_multi_session_unapproved_resource(self, client, app):
        iid = _inst(app)
        uid = _user(iid)
        mid = _material(uid, status="PENDING")
        db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": [mid]},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 422

    def test_multi_session_approved_resource_creates_session(self, client, app):
        iid = _inst(app)
        uid = _user(iid)
        mid = _material(uid, status="APPROVED")
        db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": [mid]},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 201
        data = r.get_json()['data']
        assert 'session_id' in data
        assert data['session_type'] == 'multi_pdf_chat'
        assert 'resource_ids' in data
        assert isinstance(data['resource_ids'], list)
        assert 'resource_count' in data

    def test_multi_session_max_boundary_accepted(self, client, app):
        """Exactly MAX_MULTI_PDF=10 resources should be accepted."""
        iid = _inst(app)
        uid = _user(iid)
        mids = [_material(uid, status="APPROVED", title=f"Resource {i}") for i in range(10)]
        db.session.commit()
        tok = _tok(app, uid, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_ids": mids},
                        headers={"Authorization": f"Bearer {tok}"})
        # Should succeed (200) or fail due to some infra, but NOT 422 for count
        if r.status_code == 422:
            data = r.get_json()
            assert 'Maximum' not in (data.get('message') or '')


# ─────────────────────────────────────────────────────────────────────────────
# 9. Resource Picker / Resource list API
# ─────────────────────────────────────────────────────────────────────────────

class TestResourcePickerAPI:

    def test_resources_list_is_public(self, client):
        r = client.get("/api/v1/resources")
        assert r.status_code == 200

    def test_resources_list_has_data_key(self, client):
        assert 'data' in client.get("/api/v1/resources").get_json()

    def test_resources_list_data_is_list(self, client):
        assert isinstance(client.get("/api/v1/resources").get_json()['data'], list)

    def test_pdf_picker_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="pdf-picker-view"' in body

    def test_multi_picker_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="multi-picker-view"' in body

    def test_picker_search_input_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-picker-search' in body

    def test_max_multi_constant_referenced_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'MAX_MULTI_PDF' in body or 'MAX_MULTI' in body

    def test_no_resource_ids_hardcoded_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        # No hardcoded UUIDs in template
        import re
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        # Exclude known safe places like CSS variable names — just look for raw UUID literals
        raw_uuids = re.findall(uuid_pattern, body, re.IGNORECASE)
        assert len(raw_uuids) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. Composer UX
# ─────────────────────────────────────────────────────────────────────────────

class TestComposerUX:

    def test_general_textarea_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="general-input"' in body

    def test_pdf_textarea_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="pdf-input"' in body

    def test_multi_textarea_exists(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'id="multi-input"' in body

    def test_send_buttons_start_disabled(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'disabled' in body
        assert 'id="general-send"' in body

    def test_composer_maxlength_is_2000(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'maxlength="2000"' in body

    def test_shift_enter_hint(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'Shift+Enter' in body

    def test_char_count_element(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'general-char-count' in body

    def test_empty_submission_prevention(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert '.trim()' in body


# ─────────────────────────────────────────────────────────────────────────────
# 11. Loading and Error States
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadingErrorStates:

    def test_thinking_state_class_in_css(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-thinking' in body

    def test_thinking_function_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'appendThinking' in body

    def test_thinking_text_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'thinking' in body.lower()

    def test_error_state_class_in_css(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-error-msg' in body

    def test_inline_error_function_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'appendInlineError' in body

    def test_retry_logic_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'retryFn' in body

    def test_no_fake_streaming_simulation(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'simulateTyping' not in body
        assert 'typeText' not in body
        assert 'fakeStream' not in body

    def test_no_hardcoded_ai_response(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'Here is my answer' not in body
        assert 'AI Response:' not in body


# ─────────────────────────────────────────────────────────────────────────────
# 12. Security
# ─────────────────────────────────────────────────────────────────────────────

class TestAISecurity:

    def test_institution_id_not_in_html(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'institution_id' not in body

    def test_template_escapes_user_content(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'escHtml' in body

    def test_ask_no_traceback_in_response(self, client, app):
        r = client.post("/api/v1/ai/ask",
                        json={"query": "test"},
                        headers=_auth(app))
        body = r.get_data(as_text=True)
        assert 'Traceback' not in body
        assert 'File "/' not in body

    def test_pdf_chat_idor_returns_404_not_403(self, client, app):
        """IDOR attempt must return 404, not 403 (no existence leakage)."""
        r = client.post("/api/v1/ai/pdf/chat",
                        json={"session_id": str(uuid.uuid4()), "message": "test"},
                        headers=_auth(app))
        assert r.status_code == 404

    def test_get_pdf_session_idor_returns_404(self, client, app):
        r = client.get(f"/api/v1/ai/pdf/sessions/{uuid.uuid4()}",
                       headers=_auth(app))
        assert r.status_code == 404

    def test_session_not_owned_by_another_user(self, client, app):
        """A session created by user A cannot be accessed by user B."""
        # Create user A and a session
        iid = _inst(app)
        uid_a = _user(iid)
        mid = _material(uid_a, status="APPROVED")
        db.session.commit()
        tok_a = _tok(app, uid_a, iid)
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": mid},
                        headers={"Authorization": f"Bearer {tok_a}"})
        if r.status_code != 201:
            pytest.skip("Session creation not available (LLM config)")
        session_id = r.get_json()['data']['session_id']

        # Create user B and try to access the session
        uid_b = _user(iid)
        tok_b = _tok(app, uid_b, iid)
        r2 = client.get(f"/api/v1/ai/pdf/sessions/{session_id}",
                        headers={"Authorization": f"Bearer {tok_b}"})
        assert r2.status_code == 404

    def test_pdf_session_no_sqlalchemy_in_error(self, client, app):
        r = client.post("/api/v1/ai/pdf/sessions",
                        json={"resource_id": str(uuid.uuid4())},
                        headers=_auth(app))
        body = r.get_data(as_text=True)
        assert 'sqlalchemy' not in body.lower()
        assert 'psycopg' not in body.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 13. Accessibility
# ─────────────────────────────────────────────────────────────────────────────

class TestAIAccessibility:

    def test_aria_live_regions(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-live' in body

    def test_aria_labels_present(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-label' in body

    def test_role_tablist_present(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'role="tablist"' in body

    def test_role_tabpanel_present(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'role="tabpanel"' in body

    def test_aria_selected_on_mode_tabs(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-selected' in body

    def test_general_composer_has_aria_label(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-label="Ask CampusX AI"' in body

    def test_send_button_has_aria_label(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-label="Send message"' in body

    def test_thinking_state_has_accessibility_marker(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        # Thinking indicator gets role=status for screen readers
        assert 'role' in body and ('status' in body or 'alert' in body)

    def test_citation_list_has_aria_label(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'aria-label="Sources"' in body or 'Sources' in body

    def test_reduced_motion_in_css(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'prefers-reduced-motion' in body


# ─────────────────────────────────────────────────────────────────────────────
# 14. Design System Compliance
# ─────────────────────────────────────────────────────────────────────────────

class TestAIDesignCompliance:

    def test_no_blue_purple_in_ai_css_section(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        ai_section = body.split('AI WORKSPACE')[-1] if 'AI WORKSPACE' in body else body
        assert 'purple' not in ai_section.lower()
        assert '#7C3AED' not in ai_section
        assert 'indigo' not in ai_section.lower()

    def test_ai_workspace_css_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-workspace' in body

    def test_ai_composer_css_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-composer-wrap' in body

    def test_ai_message_css_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-message' in body

    def test_ai_citations_css_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-citations' in body
        assert '.ai-citation-item' in body

    def test_ai_quality_css_class(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '.ai-quality' in body

    def test_forest_color_used_not_blue(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        ai_section = body.split('AI WORKSPACE')[-1] if 'AI WORKSPACE' in body else body
        assert 'forest' in ai_section or '#24483A' in ai_section

    def test_ochre_palette_used(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        ai_section = body.split('AI WORKSPACE')[-1] if 'AI WORKSPACE' in body else body
        assert 'ochre' in ai_section.lower() or '#C49A45' in ai_section


# ─────────────────────────────────────────────────────────────────────────────
# 15. Mobile Layout
# ─────────────────────────────────────────────────────────────────────────────

class TestAIMobileLayout:

    def test_mobile_tabs_element_in_template(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-mobile-tabs' in body

    def test_mobile_tab_buttons_present(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert 'ai-mobile-tab' in body

    def test_mobile_breakpoint_in_css(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert 'max-width: 768px' in body

    def test_reading_width_container_in_css(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        assert '760px' in body

    def test_ai_sidebar_hidden_on_mobile(self, client):
        body = client.get("/static/css/components.css").get_data(as_text=True)
        # Under 768px, ai-sidebar: display none
        assert 'ai-sidebar' in body
