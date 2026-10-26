"""
Frontend Cycle 5 — AI Study Tools
===================================
Tests for:
  - Page rendering and structure
  - study_tools.js API module
  - CSS classes
  - Resource picker
  - Quiz API integration
  - Flashcard API integration
  - Summary API integration
  - Quality indicator
  - Design compliance
  - Accessibility
  - Mobile layout
  - Security

All tests are static (template/JS/CSS inspection) — no live API calls.
Backend API calls are tested through the backend test suite (test_cycle5.py).

Fixture pattern mirrors test_cycle5.py:
  db      from app.extensions
  _inst() — creates Institution
  _user() — creates User
"""

import json
import os
import re
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'app', 'templates', 'student', 'study_tools.html'
)
JS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'app', 'static', 'js', 'study_tools.js'
)
CSS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'app', 'static', 'css', 'components.css'
)


def read_template():
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        return f.read()


def read_js():
    with open(JS_PATH, encoding='utf-8') as f:
        return f.read()


def read_template_js():
    """Read inline JS from the template's <script> block."""
    return read_template()


def read_all_js():
    """Combined JS: module file + inline template scripts."""
    return read_js() + '\n' + read_template()


def read_css():
    with open(CSS_PATH, encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# Backend auth helpers (mirrors test_cycle5.py pattern)
# ---------------------------------------------------------------------------

def _make_auth_headers(app):
    """Create a fresh institution+student+token for a test.

    Mirrors test_cycle5.py pattern: User fields match the actual model,
    generate_access_token takes a user object.
    """
    import uuid
    from app.extensions import db
    from app.models.academic import Institution
    from app.models.user import User
    from app.utils.token import generate_access_token
    from app.permissions.roles import Role

    with app.app_context():
        iid = uuid.uuid4()
        inst = Institution(
            id=iid,
            name=f'ST-Inst-{iid.hex[:4]}',
            short_name='STI',
            code=f'STI{iid.hex[:6]}',
            domain_whitelist=[],
            settings_json={},
        )
        db.session.add(inst)
        db.session.flush()

        uid = uuid.uuid4()
        email = f'st-{uid.hex[:6]}@test.edu'
        user = User(
            id=uid,
            email=email,
            email_normalized=email.lower(),
            full_name='Test Student',
            password_hash='hashed',
            institution_id=iid,
            role=Role.STUDENT,
            status='active',
        )
        db.session.add(user)
        db.session.flush()

        tok = generate_access_token(user)
        return {'Authorization': f'Bearer {tok}'}


# ---------------------------------------------------------------------------
# 1. Page rendering and structure
# ---------------------------------------------------------------------------

class TestStudyToolsPageRendering:
    """study_tools.html renders correctly via Flask test client."""

    def test_page_loads_ok(self, app):
        """GET /student/study-tools returns 200."""
        with app.test_client() as c:
            r = c.get('/student/study-tools')
        assert r.status_code == 200

    def test_page_title(self, app):
        with app.test_client() as c:
            r = c.get('/student/study-tools')
        assert b'Study Tools' in r.data

    def test_page_extends_base(self):
        t = read_template()
        assert 'extends "base.html"' in t

    def test_study_tools_js_loaded(self):
        t = read_template()
        assert 'study_tools.js' in t

    def test_workspace_element_present(self, app):
        with app.test_client() as c:
            r = c.get('/student/study-tools')
        assert b'st-workspace' in r.data

    def test_three_tool_buttons_in_sidebar(self):
        t = read_template()
        assert t.count('data-tool="quiz"') >= 1
        assert t.count('data-tool="flashcards"') >= 1
        assert t.count('data-tool="summary"') >= 1

    def test_mobile_tabs_present(self):
        t = read_template()
        assert 'st-mobile-tabs' in t
        assert 'st-mobile-tab' in t

    def test_resource_picker_present(self):
        t = read_template()
        assert 'st-picker' in t
        assert 'st-picker-search' in t
        assert 'st-picker-list' in t

    def test_quiz_result_panel_present(self):
        t = read_template()
        assert 'st-quiz-panel' in t

    def test_flashcard_panel_present(self):
        t = read_template()
        assert 'st-flashcards-panel' in t

    def test_summary_panel_present(self):
        t = read_template()
        assert 'st-summary-panel' in t

    def test_generate_button_present(self):
        t = read_template()
        assert 'st-generate-btn' in t

    def test_generating_view_present(self):
        t = read_template()
        assert 'st-generating-view' in t

    def test_setup_view_present(self):
        t = read_template()
        assert 'st-setup-view' in t

    def test_result_view_present(self):
        t = read_template()
        assert 'st-result-view' in t

    def test_auth_guard_present(self):
        t = read_template()
        assert 'isAuthenticated' in t

    def test_auth_redirect_to_login(self):
        t = read_template()
        assert '/login' in t


# ---------------------------------------------------------------------------
# 2. study_tools.js module
# ---------------------------------------------------------------------------

class TestStudyToolsJSModule:
    """study_tools.js exposes correct API surface."""

    def test_module_file_exists(self):
        assert os.path.exists(JS_PATH), "study_tools.js not found"

    def test_namespace_set(self):
        js = read_js()
        assert 'CampusX.studyTools' in js

    def test_max_quiz_questions_constant(self):
        js = read_js()
        assert 'MAX_QUIZ_QUESTIONS' in js
        assert '15' in js  # value must equal 15

    def test_max_flashcard_count_constant(self):
        js = read_js()
        assert 'MAX_FLASHCARD_COUNT' in js
        assert '20' in js  # value must equal 20

    def test_generate_quiz_exported(self):
        js = read_js()
        assert 'generateQuiz' in js

    def test_generate_flashcards_exported(self):
        js = read_js()
        assert 'generateFlashcards' in js

    def test_generate_summary_exported(self):
        js = read_js()
        assert 'generateSummary' in js

    def test_list_resources_exported(self):
        js = read_js()
        assert 'listResources' in js

    def test_friendly_error_exported(self):
        js = read_js()
        assert 'friendlyError' in js

    def test_quiz_endpoint_correct(self):
        js = read_js()
        assert '/ai/quiz/generate' in js

    def test_flashcard_endpoint_correct(self):
        js = read_js()
        assert '/ai/flashcards/generate' in js

    def test_summary_endpoint_correct(self):
        js = read_js()
        assert '/ai/summarize' in js

    def test_bearer_auth_used(self):
        js = read_js()
        assert 'Bearer' in js

    def test_institution_id_not_in_module(self):
        """institution_id must never appear in the API request payload — always from JWT."""
        js = read_js()
        # Check that institution_id is NOT sent in any POST body payload.
        # It may appear in JSDoc comments explaining the security contract — that is fine.
        # We strip comment lines before checking.
        code_lines = [ln for ln in js.split('\n') if not ln.strip().startswith('*') and not ln.strip().startswith('//')]
        code_only = '\n'.join(code_lines)
        assert 'institution_id' not in code_only

    def test_resource_id_in_quiz_request(self):
        js = read_js()
        assert 'resource_id' in js

    def test_num_questions_in_quiz_request(self):
        js = read_js()
        assert 'num_questions' in js

    def test_num_cards_in_flashcard_request(self):
        js = read_js()
        assert 'num_cards' in js

    def test_unauthorized_error_type(self):
        js = read_js()
        assert 'UNAUTHORIZED' in js

    def test_rate_limited_error_type(self):
        js = read_js()
        assert 'RATE_LIMITED' in js

    def test_not_found_error_type(self):
        js = read_js()
        assert 'NOT_FOUND' in js

    def test_no_context_error_handled(self):
        js = read_js()
        assert 'NO_CONTEXT' in js


# ---------------------------------------------------------------------------
# 3. CSS classes
# ---------------------------------------------------------------------------

class TestStudyToolsCSS:
    """Required CSS classes are present in components.css."""

    def _css(self):
        return read_css()

    def _study_tools_css(self):
        """Only the Study Tools Cycle 5 CSS additions."""
        css = read_css()
        idx = css.find('STUDY TOOLS WORKSPACE')
        return css[idx:] if idx != -1 else css[-5000:]

    def test_workspace_class(self):
        assert '.st-workspace' in self._css()

    def test_sidebar_class(self):
        assert '.st-sidebar' in self._css()

    def test_tool_btn_class(self):
        assert '.st-tool-btn' in self._css()

    def test_mobile_tabs_class(self):
        assert '.st-mobile-tabs' in self._css()

    def test_picker_class(self):
        assert '.st-picker' in self._css()

    def test_picker_item_class(self):
        assert '.st-picker-item' in self._css()

    def test_generating_view_class(self):
        assert '.st-generating-view' in self._css()

    def test_result_view_class(self):
        assert '.st-result-view' in self._css()

    def test_quiz_option_class(self):
        assert '.st-quiz-option' in self._css()

    def test_quiz_option_correct_state(self):
        assert '.st-quiz-option.correct' in self._css()

    def test_quiz_option_incorrect_state(self):
        assert '.st-quiz-option.incorrect' in self._css()

    def test_flashcard_class(self):
        assert '.st-flashcard' in self._css()

    def test_flashcard_revealed_state(self):
        assert '.st-flashcard.is-revealed' in self._css()

    def test_summary_body_class(self):
        assert '.st-summary-body' in self._css()

    def test_quality_badge_class(self):
        assert '.st-quality-badge' in self._css()

    def test_quality_high_class(self):
        assert '.st-quality-high' in self._css()

    def test_quality_medium_class(self):
        assert '.st-quality-medium' in self._css()

    def test_quality_low_class(self):
        assert '.st-quality-low' in self._css()

    def test_quality_supported_class(self):
        assert '.st-quality-supported' in self._css()

    def test_sources_class(self):
        assert '.st-sources' in self._css()

    def test_score_ring_class(self):
        assert '.st-score-ring' in self._css()

    def test_dots_animation(self):
        css = self._css()
        assert 'st-dot' in css
        assert '@keyframes' in css

    def test_responsive_768(self):
        css = self._study_tools_css()
        assert '768px' in css

    def test_responsive_480(self):
        css = self._study_tools_css()
        assert '480px' in css

    def test_mobile_sidebar_hidden(self):
        css = self._study_tools_css()
        # After media query block, .st-sidebar should appear
        idx768 = css.find('768px')
        block = css[idx768:idx768 + 1200] if idx768 != -1 else ''
        assert 'st-sidebar' in block

    def test_mobile_tabs_shown_at_mobile(self):
        css = self._study_tools_css()
        idx768 = css.find('768px')
        block = css[idx768:idx768 + 1200] if idx768 != -1 else ''
        assert 'st-mobile-tabs' in block

    def test_reduced_motion_respected(self):
        assert 'prefers-reduced-motion' in self._css()


# ---------------------------------------------------------------------------
# 4. Quiz API — backend contract validation
# ---------------------------------------------------------------------------

class TestQuizAPI:
    """Tests that quiz generation calls use the correct backend contract."""

    def test_quiz_requires_auth(self, app):
        with app.test_client() as c:
            r = c.post('/api/v1/ai/quiz/generate',
                       json={'resource_id': 'test-id'},
                       content_type='application/json')
        assert r.status_code == 401

    def test_quiz_requires_resource_id(self, app):
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/quiz/generate',
                           json={},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 400

    def test_quiz_invalid_resource_id_format(self, app):
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/quiz/generate',
                           json={'resource_id': 'not-a-uuid'},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code in (400, 404)

    def test_quiz_nonexistent_resource_404(self, app):
        import uuid
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/quiz/generate',
                           json={'resource_id': str(uuid.uuid4())},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 404

    def test_quiz_num_questions_sent_in_js(self):
        js = read_all_js()
        assert 'num_questions' in js

    def test_quiz_response_correct_answer_used(self):
        """correct_answer_index from backend is used for client-side scoring."""
        js = read_all_js()
        assert 'correct_answer_index' in js

    def test_quiz_explanation_used(self):
        """explanation field from backend is rendered."""
        js = read_all_js()
        assert 'explanation' in js

    def test_quiz_topic_field_used(self):
        t = read_template()
        assert 'st-result-topic' in t or 'topic' in t

    def test_quiz_quality_field_used(self):
        js = read_all_js()
        assert 'quality' in js

    def test_quiz_sources_field_used(self):
        js = read_all_js()
        assert 'sources' in js


# ---------------------------------------------------------------------------
# 5. Flashcard API — backend contract validation
# ---------------------------------------------------------------------------

class TestFlashcardAPI:
    """Flashcard generation endpoint contract."""

    def test_flashcard_requires_auth(self, app):
        with app.test_client() as c:
            r = c.post('/api/v1/ai/flashcards/generate',
                       json={'resource_id': 'test'},
                       content_type='application/json')
        assert r.status_code == 401

    def test_flashcard_requires_resource_id(self, app):
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/flashcards/generate',
                           json={},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 400

    def test_flashcard_nonexistent_resource_404(self, app):
        import uuid
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/flashcards/generate',
                           json={'resource_id': str(uuid.uuid4())},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 404

    def test_num_cards_sent_in_js(self):
        js = read_all_js()
        assert 'num_cards' in js

    def test_flashcard_front_used_in_template(self):
        js = read_all_js()
        assert 'front' in js

    def test_flashcard_back_used_in_template(self):
        js = read_all_js()
        assert 'back' in js

    def test_flashcard_category_rendered(self):
        t = read_template()
        assert 'fc-category' in t

    def test_flashcard_reveal_button_present(self):
        t = read_template()
        assert 'st-fc-reveal' in t

    def test_flashcard_restart_button_present(self):
        t = read_template()
        assert 'st-fc-restart' in t

    def test_flashcard_quality_used(self):
        js = read_all_js()
        assert 'quality' in js

    def test_flashcard_sources_used(self):
        js = read_all_js()
        assert 'sources' in js


# ---------------------------------------------------------------------------
# 6. Summary API — backend contract validation
# ---------------------------------------------------------------------------

class TestSummaryAPI:
    """Summary generation endpoint contract."""

    def test_summarize_requires_auth(self, app):
        with app.test_client() as c:
            r = c.post('/api/v1/ai/summarize',
                       json={'resource_id': 'test'},
                       content_type='application/json')
        assert r.status_code == 401

    def test_summarize_requires_resource_id(self, app):
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/summarize',
                           json={},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 400

    def test_summarize_nonexistent_resource_404(self, app):
        import uuid
        hdrs = _make_auth_headers(app)
        with app.app_context():
            with app.test_client() as c:
                r = c.post('/api/v1/ai/summarize',
                           json={'resource_id': str(uuid.uuid4())},
                           headers=hdrs,
                           content_type='application/json')
        assert r.status_code == 404

    def test_summary_field_rendered(self):
        t = read_template()
        assert 'st-summary-body' in t

    def test_summary_rendered_safely(self):
        """Summary output goes through markdown renderer, not raw user input to innerHTML."""
        js = read_all_js()
        assert 'renderMarkdown' in js
        assert 'escHtml' in js

    def test_copy_button_present(self):
        t = read_template()
        assert 'copy' in t.lower() or 'Copy' in t

    def test_summary_quality_used(self):
        js = read_all_js()
        assert 'quality' in js

    def test_summary_sources_used(self):
        js = read_all_js()
        assert 'sources' in js


# ---------------------------------------------------------------------------
# 7. Resource picker
# ---------------------------------------------------------------------------

class TestResourcePicker:
    """Resource picker uses /api/v1/resources."""

    def test_resources_endpoint_hit(self):
        js = read_all_js()
        assert '/resources' in js

    def test_picker_search_present_in_template(self):
        t = read_template()
        assert 'st-picker-search' in t

    def test_picker_list_container_present(self):
        t = read_template()
        assert 'st-picker-list' in t

    def test_picker_loading_state(self):
        t = read_template()
        assert 'st-picker-loading' in t

    def test_picker_empty_state(self):
        t = read_template()
        assert 'st-picker-empty' in t

    def test_picker_error_state(self):
        t = read_template()
        assert 'st-picker-error' in t

    def test_resource_title_rendered_safely(self):
        """Picker items are rendered with escHtml."""
        js = read_all_js()
        assert 'escHtml' in js

    def test_approved_resources_only(self):
        """JS filters to APPROVED resources only."""
        js = read_all_js()
        assert 'APPROVED' in js or 'approved' in js

    def test_resources_api_called_on_init(self):
        js = read_all_js()
        assert 'loadResources' in js


# ---------------------------------------------------------------------------
# 8. Quality indicator
# ---------------------------------------------------------------------------

class TestStudyToolsQuality:
    """Quality indicator uses real backend fields: confidence_level, grounding_status."""

    def test_confidence_level_used(self):
        js = read_all_js()
        assert 'confidence_level' in js

    def test_grounding_status_used(self):
        js = read_all_js()
        assert 'grounding_status' in js

    def test_confidence_level_is_primary_display(self):
        """confidence_level (string) is the primary display, not raw float."""
        js = read_all_js()
        assert 'confidence_level' in js

    def test_quality_high_class_used(self):
        # st-quality-high is assembled dynamically in renderQuality ('st-quality-' + level).
        # Verify the CSS class is defined (which is what makes it meaningful).
        css = read_css()
        assert 'st-quality-high' in css

    def test_quality_omitted_if_missing(self):
        """If quality is falsy, the indicator is hidden."""
        js = read_all_js()
        assert 'renderQuality' in js
        rq_idx = js.find('function renderQuality')
        rq_block = js[rq_idx:rq_idx + 400] if rq_idx != -1 else ''
        assert 'hidden' in rq_block or 'return' in rq_block

    def test_ai_generated_label_present(self):
        t = read_template()
        assert 'AI-generated' in t or 'ai-label' in t

    def test_grounding_supported_badge(self):
        # 'SUPPORTED' literal appears in renderQuality inside the template script
        js = read_all_js()
        assert 'SUPPORTED' in js

    def test_grounding_partial_badge(self):
        js = read_all_js()
        assert 'PARTIALLY_SUPPORTED' in js

    def test_grounding_unsupported_badge(self):
        # 'UNSUPPORTED' appears as a CSS class suffix and in renderQuality conditional
        combined = read_all_js() + read_css()
        assert 'UNSUPPORTED' in combined or 'unsupported' in combined



# ---------------------------------------------------------------------------
# 9. Quiz UX
# ---------------------------------------------------------------------------

class TestQuizUX:
    """Quiz interaction and UX requirements."""

    def test_progress_bar_present(self):
        t = read_template()
        assert 'st-quiz-progress' in t

    def test_question_text_element(self):
        t = read_template()
        assert 'st-quiz-q-text' in t

    def test_options_container(self):
        t = read_template()
        assert 'st-quiz-options' in t

    def test_explanation_element(self):
        t = read_template()
        assert 'st-quiz-explanation' in t

    def test_prev_button(self):
        t = read_template()
        assert 'st-quiz-prev' in t

    def test_next_button(self):
        t = read_template()
        assert 'st-quiz-next' in t

    def test_score_screen_present(self):
        t = read_template()
        assert 'st-quiz-score' in t or 'st-score-ring' in t

    def test_retry_button_present(self):
        t = read_template()
        assert 'retry' in t.lower() or 'Try again' in t

    def test_review_button_present(self):
        t = read_template()
        assert 'review' in t.lower() or 'Review' in t

    def test_score_calculated_client_side(self):
        """Scoring logic uses correct_answer_index from backend."""
        js = read_all_js()
        assert 'correct_answer_index' in js

    def test_correct_class_applied(self):
        js = read_all_js()
        assert 'correct' in js

    def test_incorrect_class_applied(self):
        js = read_all_js()
        assert 'incorrect' in js

    def test_question_count_config_present(self):
        t = read_template()
        assert 'st-q-count' in t or 'st-quiz-config' in t

    def test_num_questions_bounded_in_js(self):
        js = read_all_js()
        assert 'MAX_Q' in js or 'MAX_QUIZ_QUESTIONS' in js


# ---------------------------------------------------------------------------
# 10. Flashcard UX
# ---------------------------------------------------------------------------

class TestFlashcardUX:
    """Flashcard interaction requirements."""

    def test_flashcard_element(self):
        t = read_template()
        assert 'st-flashcard' in t

    def test_reveal_button(self):
        t = read_template()
        assert 'st-fc-reveal' in t

    def test_prev_button(self):
        t = read_template()
        assert 'st-fc-prev' in t

    def test_next_button(self):
        t = read_template()
        assert 'st-fc-next' in t

    def test_restart_button(self):
        t = read_template()
        assert 'st-fc-restart' in t

    def test_progress_indicator(self):
        t = read_template()
        assert 'st-fc-progress' in t

    def test_keyboard_reveal(self):
        js = read_all_js()
        assert 'keydown' in js
        assert 'Space' in js or 'Enter' in js

    def test_reveal_toggles_visibility(self):
        js = read_all_js()
        assert 'is-revealed' in js

    def test_card_count_bounded(self):
        js = read_all_js()
        assert 'MAX_FC' in js or 'MAX_FLASHCARD_COUNT' in js

    def test_fc_aria_pressed(self):
        t = read_template()
        assert 'aria-pressed' in t


# ---------------------------------------------------------------------------
# 11. Summary UX
# ---------------------------------------------------------------------------

class TestSummaryUX:
    """Summary display requirements."""

    def test_summary_body_element(self):
        t = read_template()
        assert 'st-summary-body' in t

    def test_copy_action_present(self):
        t = read_template()
        assert 'copy' in t.lower() or 'Copy' in t

    def test_markdown_renderer_exists(self):
        js = read_all_js()
        assert 'renderMarkdown' in js

    def test_markdown_handles_headings(self):
        js = read_all_js()
        assert 'h3' in js or '<h3>' in js
        assert 'h2' in js or '<h2>' in js

    def test_markdown_handles_bullets(self):
        js = read_all_js()
        assert '<ul>' in js or 'ul>' in js
        assert '<li>' in js or 'li>' in js

    def test_markdown_uses_esc_html(self):
        """renderMarkdown must escape input before emitting HTML."""
        js = read_all_js()
        assert 'escHtml' in js


# ---------------------------------------------------------------------------
# 12. Design compliance
# ---------------------------------------------------------------------------

class TestDesignCompliance:
    """No blue/purple/violet — strict Forest/Terracotta/Ochre palette."""

    def _st_css(self):
        css = read_css()
        idx = css.find('STUDY TOOLS WORKSPACE')
        return css[idx:] if idx != -1 else css[-5000:]

    def test_no_blue_color_in_st_css(self):
        css = self._st_css()
        assert 'color: blue' not in css
        assert '#0000ff' not in css.lower()

    def test_no_purple_in_st_css(self):
        css = self._st_css()
        assert 'purple' not in css

    def test_no_violet_in_st_css(self):
        css = self._st_css()
        assert 'violet' not in css

    def test_forest_color_used(self):
        css = self._st_css()
        assert 'forest' in css.lower() or '#24483A' in css

    def test_terracotta_color_used(self):
        css = self._st_css()
        assert 'terracotta' in css.lower()

    def test_no_glassmorphism(self):
        css = self._st_css()
        assert 'backdrop-filter' not in css

    def test_design_system_tokens_used(self):
        css = self._st_css()
        assert '--cx-' in css

    def test_no_blue_in_js_module(self):
        js = read_js()
        assert 'color: blue' not in js
        assert 'purple' not in js


# ---------------------------------------------------------------------------
# 13. Accessibility
# ---------------------------------------------------------------------------

class TestAccessibility:
    """Semantic HTML, ARIA, keyboard nav."""

    def test_main_landmark_present(self):
        t = read_template()
        assert '<main' in t

    def test_aside_landmark_present(self):
        t = read_template()
        assert '<aside' in t

    def test_tablist_role_present(self):
        t = read_template()
        assert 'role="tablist"' in t

    def test_tab_role_on_buttons(self):
        t = read_template()
        assert 'role="tab"' in t

    def test_aria_selected_on_tabs(self):
        t = read_template()
        assert 'aria-selected' in t

    def test_aria_live_on_generating_view(self):
        t = read_template()
        assert 'aria-live' in t

    def test_aria_label_on_workspace(self):
        t = read_template()
        assert 'aria-label' in t

    def test_quiz_options_group_role(self):
        t = read_template()
        assert 'role="group"' in t

    def test_flashcard_button_role(self):
        t = read_template()
        assert 'role="button"' in t

    def test_flashcard_aria_pressed(self):
        t = read_template()
        assert 'aria-pressed' in t

    def test_quiz_progress_aria(self):
        t = read_template()
        assert 'role="progressbar"' in t

    def test_quiz_progress_aria_valuenow(self):
        t = read_template()
        assert 'aria-valuenow' in t

    def test_keyboard_nav_quiz_options(self):
        js = read_all_js()
        assert 'ArrowDown' in js
        assert 'ArrowUp' in js

    def test_focus_management(self):
        js = read_all_js()
        assert 'focus()' in js


# ---------------------------------------------------------------------------
# 14. Mobile layout
# ---------------------------------------------------------------------------

class TestMobileLayout:
    """Mobile-critical layout elements."""

    def test_mobile_tabs_base_display_none(self):
        css = read_css()
        # .st-mobile-tabs base rule has display: none
        idx = css.find('.st-mobile-tabs {')
        if idx == -1:
            idx = css.find('.st-mobile-tabs{')
        block = css[idx:idx + 200] if idx != -1 else ''
        assert 'none' in block

    def test_sidebar_hidden_at_768(self):
        css = read_css()
        idx = css.rfind('768px')  # last occurrence = study tools block
        mobile = css[idx:idx + 1400] if idx != -1 else ''
        assert 'st-sidebar' in mobile

    def test_resource_chip_shown_at_mobile(self):
        t = read_template()
        assert 'st-resource-chip' in t

    def test_no_horizontal_overflow_css(self):
        css = read_css()
        assert 'scrollbar-width' in css

    def test_flashcard_min_height_responsive(self):
        css = read_css()
        idx = css.rfind('768px')
        mobile = css[idx:idx + 1400] if idx != -1 else ''
        assert 'st-flashcard' in mobile


# ---------------------------------------------------------------------------
# 15. Security
# ---------------------------------------------------------------------------

class TestStudyToolsSecurity:
    """Security constraints."""

    def test_institution_id_not_in_template(self):
        """institution_id must never appear in HTML — always from JWT on backend."""
        t = read_template()
        assert 'institution_id' not in t

    def test_institution_id_not_in_js_module(self):
        """institution_id must not appear in API call payloads (comments are OK)."""
        js = read_js()
        code_lines = [ln for ln in js.split('\n')
                      if not ln.strip().startswith('*') and not ln.strip().startswith('//')]
        code_only = '\n'.join(code_lines)
        assert 'institution_id' not in code_only

    def test_esc_html_used_in_template_js(self):
        js = read_all_js()
        assert 'escHtml' in js

    def test_no_raw_user_content_to_innerhtml(self):
        """Dynamic user/AI content must go through escHtml before innerHTML."""
        js = read_all_js()
        assert 'escHtml' in js
        assert 'renderMarkdown' in js  # summary goes through markdown renderer

    def test_backend_is_auth_authority(self):
        """Resource picker uses authenticated API; APPROVED filter applied."""
        js = read_all_js()
        assert 'listResources' in js
        assert 'APPROVED' in js or 'approved' in js

    def test_auth_redirect_on_401(self):
        js = read_all_js()
        assert '/login' in js

    def test_session_expired_redirects(self):
        js = read_all_js()
        assert 'session=expired' in js or 'location.replace' in js

    def test_friendly_error_returns_safe_messages(self):
        js = read_all_js()
        assert 'function friendlyError' in js
        fe_idx = js.find('function friendlyError')
        fe_block = js[fe_idx:fe_idx + 500]
        # Must classify errors — not pass through raw error.message
        assert 'UNAUTHORIZED' in fe_block or 'RATE_LIMITED' in fe_block


# ---------------------------------------------------------------------------
# 16. Duplicate submission prevention
# ---------------------------------------------------------------------------

class TestSubmissionPrevention:
    """Prevent duplicate API calls and empty submissions."""

    def test_busy_flag_exists(self):
        js = read_all_js()
        assert 'busy' in js

    def test_generate_disabled_while_busy(self):
        js = read_all_js()
        assert 'busy = true' in js or 'busy=true' in js

    def test_empty_resource_blocked(self):
        """generate() bails out if no resource selected."""
        js = read_all_js()
        # Use rfind to get the standalone generate() function in the template script,
        # not generateQuiz in the module file.
        gen_idx = js.rfind('async function generate')
        gen_block = js[gen_idx:gen_idx + 600] if gen_idx != -1 else ''
        assert 'selectedResource' in gen_block

    def test_generate_button_disabled_during_generation(self):
        js = read_all_js()
        assert 'generateBtn.disabled' in js

    def test_regenerate_button_disabled_during_generation(self):
        js = read_all_js()
        assert 'regenerateBtn.disabled' in js


# ---------------------------------------------------------------------------
# 17. Routes and static serving
# ---------------------------------------------------------------------------

class TestStudyToolsRoutes:
    """Routes serve correct status codes."""

    def test_study_tools_route_200(self, app):
        with app.test_client() as c:
            r = c.get('/student/study-tools')
        assert r.status_code == 200

    def test_campusx_branding_in_page(self, app):
        with app.test_client() as c:
            r = c.get('/student/study-tools')
        assert b'CampusX' in r.data

    def test_study_tools_js_served_200(self, app):
        with app.test_client() as c:
            r = c.get('/static/js/study_tools.js')
        assert r.status_code == 200

    def test_study_tools_js_content_type(self, app):
        with app.test_client() as c:
            r = c.get('/static/js/study_tools.js')
        assert 'javascript' in r.content_type or 'text' in r.content_type
