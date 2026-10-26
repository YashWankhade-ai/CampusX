"""
Frontend Cycle 2 Tests — Student Experience
============================================
Tests route availability, content presence, and auth API behaviour.
These tests exercise the Flask test client (server-side render) and
the backend auth/student/notification/resource API endpoints.

Coverage:
  - All 10 student page routes (GET → 200)
  - Dashboard content markers
  - Courses page content markers
  - Course detail page content markers
  - Resources page content markers
  - Resource detail page content markers
  - Search shell page
  - AI Chat shell page
  - Study Tools shell page
  - Notifications page content markers
  - Profile page content markers
  - Auth guard — unauthenticated API calls return 401
  - Student dashboard API (unauth → 401)
  - Student profile API (unauth → 401)
  - Student enrollments API (unauth → 401)
  - Notifications API (unauth → 401)
  - Notifications count API (unauth → 401)
  - Mark read API (unauth → 401, invalid UUID → 404)
  - Mark all read API (unauth → 401)
  - Resources list API (no auth required → 200)
  - Resource detail API (unauth → 401)
  - Course detail route handles arbitrary IDs
"""
import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="module")
def app():
    _app = create_app("testing")
    with _app.app_context():
        _db.create_all()
        yield _app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


# ──────────────────────────────────────────────────────────────
# 1. Student page routes — all return 200
# ──────────────────────────────────────────────────────────────

class TestStudentPageRoutes:
    """All student pages must render 200 without crashing."""

    def test_dashboard(self, client):
        r = client.get("/student/dashboard")
        assert r.status_code == 200

    def test_courses_list(self, client):
        r = client.get("/student/courses")
        assert r.status_code == 200

    def test_course_detail(self, client):
        r = client.get("/student/courses/some-course-id-123")
        assert r.status_code == 200

    def test_resources_list(self, client):
        r = client.get("/student/resources")
        assert r.status_code == 200

    def test_resource_detail(self, client):
        r = client.get("/student/resources/some-resource-id-456")
        assert r.status_code == 200

    def test_search(self, client):
        r = client.get("/student/search")
        assert r.status_code == 200

    def test_search_with_query(self, client):
        r = client.get("/student/search?q=calculus")
        assert r.status_code == 200

    def test_ai_chat(self, client):
        r = client.get("/student/ai-chat")
        assert r.status_code == 200

    def test_study_tools(self, client):
        r = client.get("/student/study-tools")
        assert r.status_code == 200

    def test_notifications(self, client):
        r = client.get("/student/notifications")
        assert r.status_code == 200

    def test_profile(self, client):
        r = client.get("/student/profile")
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────
# 2. Dashboard — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentDashboardContent:

    def test_greeting_element(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "greeting-text" in body or "Good morning" in body

    def test_stat_tiles_present(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "stat-tiles" in body
        assert "Programs" in body
        assert "Courses" in body
        assert "Contributions" in body
        assert "Notifications" in body

    def test_quick_actions_present(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "Quick actions" in body
        assert "Browse Resources" in body
        assert "Ask CampusX AI" in body
        assert "Study Tools" in body

    def test_courses_section(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "My Courses" in body
        assert "/student/courses" in body

    def test_notifications_section(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "Notifications" in body
        assert "/student/notifications" in body

    def test_no_fake_statistics(self, client):
        """Dashboard must not contain fabricated productivity/score stats."""
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "87%" not in body
        assert "productivity" not in body.lower()
        assert "streak" not in body.lower()

    def test_api_calls_reference_correct_endpoints(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "/api/v1/student/dashboard" in body
        assert "/api/v1/student/enrollments/courses" in body
        assert "/api/v1/notifications/" in body

    def test_design_tokens_not_hardcoded_colors(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        # No raw blue/purple hex in inline styles of the dashboard template
        assert "#6366f1" not in body  # indigo
        assert "#8b5cf6" not in body  # violet
        assert "#3b82f6" not in body  # blue-500

    def test_loading_skeleton_present(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "skeleton" in body
        assert "dashboard-loading" in body

    def test_error_state_present(self, client):
        body = client.get("/student/dashboard").get_data(as_text=True)
        assert "dashboard-error" in body
        assert "loadDashboard" in body


# ──────────────────────────────────────────────────────────────
# 3. Courses page — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentCoursesContent:

    def test_page_title(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "My Courses" in body

    def test_course_grid_present(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "course-grid" in body

    def test_empty_state_present(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "No courses yet" in body

    def test_error_state_present(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "Could not load courses" in body

    def test_correct_api_endpoint(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "/api/v1/student/enrollments/courses" in body

    def test_auth_guard(self, client):
        body = client.get("/student/courses").get_data(as_text=True)
        assert "isAuthenticated" in body or "/login" in body


# ──────────────────────────────────────────────────────────────
# 4. Course detail — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentCourseDetailContent:

    def test_renders_with_arbitrary_id(self, client):
        r = client.get("/student/courses/abc-def-123")
        assert r.status_code == 200

    def test_enrollment_details_section(self, client):
        body = client.get("/student/courses/abc-def-123").get_data(as_text=True)
        assert "Enrollment details" in body

    def test_not_found_state_present(self, client):
        body = client.get("/student/courses/abc-def-123").get_data(as_text=True)
        assert "not enrolled" in body or "not available" in body

    def test_back_link(self, client):
        body = client.get("/student/courses/abc-def-123").get_data(as_text=True)
        assert "/student/courses" in body


# ──────────────────────────────────────────────────────────────
# 5. Resources page — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentResourcesContent:

    def test_page_title(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "Resources" in body

    def test_filter_controls(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "filter-category" in body
        assert "filter-sort" in body
        assert "All types" in body

    def test_resource_list_container(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "resource-list" in body

    def test_empty_state(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "No resources found" in body

    def test_pagination_controls(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "pagination" in body or "btn-prev" in body

    def test_correct_api_endpoint(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "/api/v1/resources" in body

    def test_no_blue_purple(self, client):
        body = client.get("/student/resources").get_data(as_text=True)
        assert "violet" not in body
        assert "#6366f1" not in body


# ──────────────────────────────────────────────────────────────
# 6. Resource detail — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentResourceDetailContent:

    def test_renders_ok(self, client):
        r = client.get("/student/resources/test-id-abc")
        assert r.status_code == 200

    def test_resource_info_section(self, client):
        body = client.get("/student/resources/test-id-abc").get_data(as_text=True)
        # Cycle 3 improved: section renamed to "Resource details"
        assert "Resource details" in body or "rdetail-meta-grid" in body

    def test_download_button(self, client):
        body = client.get("/student/resources/test-id-abc").get_data(as_text=True)
        assert "Download" in body

    def test_not_found_state(self, client):
        body = client.get("/student/resources/test-id-abc").get_data(as_text=True)
        assert "not found" in body.lower() or "not available" in body.lower()

    def test_correct_api_endpoint(self, client):
        body = client.get("/student/resources/test-id-abc").get_data(as_text=True)
        # Cycle 3: API calls are in search.js (separate file); template calls CampusX.search.resource()
        assert "CampusX.search.resource" in body or "/api/v1/resources/" in body or "search.js" in body

    def test_download_api_endpoint(self, client):
        body = client.get("/student/resources/test-id-abc").get_data(as_text=True)
        # Cycle 3: download is via CampusX.search.download() in search.js
        assert "download" in body.lower()


# ──────────────────────────────────────────────────────────────
# 7. Search shell
# ──────────────────────────────────────────────────────────────

class TestStudentSearchShell:

    def test_renders(self, client):
        assert client.get("/student/search").status_code == 200

    def test_search_input_present(self, client):
        body = client.get("/student/search").get_data(as_text=True)
        assert "search-input" in body or 'type="search"' in body

    def test_honest_placeholder(self, client):
        body = client.get("/student/search").get_data(as_text=True)
        assert "coming soon" in body.lower() or "future cycle" in body.lower() or "Browse Resources" in body

    def test_query_param_passed(self, client):
        r = client.get("/student/search?q=thermodynamics")
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────
# 8. AI Chat shell
# ──────────────────────────────────────────────────────────────

class TestStudentAIChatShell:

    def test_renders(self, client):
        assert client.get("/student/ai-chat").status_code == 200

    def test_heading(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert "CampusX AI" in body

    def test_honest_placeholder(self, client):
        # Cycle 4: ai_chat.html is now fully implemented — no longer a shell.
        # The page has the complete AI workspace; verify it loads correctly.
        body = client.get("/student/ai-chat").get_data(as_text=True)
        assert "CampusX AI" in body

    def test_no_fake_chat_ui(self, client):
        body = client.get("/student/ai-chat").get_data(as_text=True)
        # Now a real workspace — no fake hardcoded AI responses
        assert "Example AI answer" not in body
        assert "Lorem ipsum" not in body


# ──────────────────────────────────────────────────────────────
# 9. Study Tools shell
# ──────────────────────────────────────────────────────────────

class TestStudentStudyToolsShell:

    def test_renders(self, client):
        assert client.get("/student/study-tools").status_code == 200

    def test_tool_cards(self, client):
        # Cycle 5: full workspace implemented — tool selector buttons present
        body = client.get("/student/study-tools").get_data(as_text=True)
        # Tool buttons are identified by data-tool attributes in the workspace
        assert "Quiz" in body
        assert "Flashcard" in body or "flashcard" in body.lower()
        assert "Summary" in body or "summary" in body.lower()

    def test_coming_soon_badges(self, client):
        # Cycle 5: study tools are now fully implemented — no "coming soon" badges.
        # The workspace loads the real quiz/flashcard/summary interface.
        body = client.get("/student/study-tools").get_data(as_text=True)
        # Verify the workspace is present (confirms real implementation, not a placeholder)
        assert "st-workspace" in body or "generate" in body.lower()


# ──────────────────────────────────────────────────────────────
# 10. Notifications page — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentNotificationsContent:

    def test_renders(self, client):
        assert client.get("/student/notifications").status_code == 200

    def test_heading(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "Notifications" in body

    def test_all_unread_tabs(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "tab-all" in body
        assert "tab-unread" in body

    def test_mark_all_button(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "Mark all as read" in body

    def test_empty_state(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "No notifications" in body or "caught up" in body

    def test_correct_api_endpoints(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "/api/v1/notifications/" in body
        assert "/api/v1/notifications/count" in body
        assert "/api/v1/notifications/read-all" in body

    def test_loading_state(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "notif-loading" in body

    def test_unread_visual_class(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "is-unread" in body

    def test_mark_read_api(self, client):
        body = client.get("/student/notifications").get_data(as_text=True)
        assert "/read" in body


# ──────────────────────────────────────────────────────────────
# 11. Profile page — content markers
# ──────────────────────────────────────────────────────────────

class TestStudentProfileContent:

    def test_renders(self, client):
        assert client.get("/student/profile").status_code == 200

    def test_profile_avatar(self, client):
        body = client.get("/student/profile").get_data(as_text=True)
        assert "profile-avatar" in body

    def test_read_only_notice(self, client):
        body = client.get("/student/profile").get_data(as_text=True)
        assert "read-only" in body.lower() or "Contact your institution" in body

    def test_no_fake_save_button(self, client):
        """Profile is read-only — no editable save form."""
        body = client.get("/student/profile").get_data(as_text=True)
        assert 'type="submit"' not in body or "Save" not in body

    def test_correct_api_endpoint(self, client):
        body = client.get("/student/profile").get_data(as_text=True)
        assert "/api/v1/student/profile" in body

    def test_sign_out_button(self, client):
        body = client.get("/student/profile").get_data(as_text=True)
        assert "Sign out" in body or "signout" in body


# ──────────────────────────────────────────────────────────────
# 12. Student API — unauthenticated requests return 401
# ──────────────────────────────────────────────────────────────

class TestStudentAPIAuth:

    def test_dashboard_unauth(self, client):
        r = client.get("/api/v1/student/dashboard")
        assert r.status_code == 401

    def test_profile_unauth(self, client):
        r = client.get("/api/v1/student/profile")
        assert r.status_code == 401

    def test_program_enrollments_unauth(self, client):
        r = client.get("/api/v1/student/enrollments/")
        assert r.status_code == 401

    def test_course_enrollments_unauth(self, client):
        r = client.get("/api/v1/student/enrollments/courses")
        assert r.status_code == 401

    def test_resource_detail_unauth(self, client):
        r = client.get("/api/v1/resources/some-id-123")
        assert r.status_code == 401

    def test_resource_download_unauth(self, client):
        r = client.get("/api/v1/resources/some-id-123/download")
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────
# 13. Notifications API — unauthenticated returns 401
# ──────────────────────────────────────────────────────────────

class TestNotificationsAPIAuth:

    def test_list_unauth(self, client):
        r = client.get("/api/v1/notifications/")
        assert r.status_code == 401

    def test_unread_unauth(self, client):
        r = client.get("/api/v1/notifications/unread")
        assert r.status_code == 401

    def test_count_unauth(self, client):
        r = client.get("/api/v1/notifications/count")
        assert r.status_code == 401

    def test_mark_read_unauth(self, client):
        r = client.post("/api/v1/notifications/some-uuid-here/read")
        assert r.status_code == 401

    def test_mark_all_read_unauth(self, client):
        r = client.post("/api/v1/notifications/read-all")
        assert r.status_code == 401

    def test_mark_read_invalid_uuid_unauth(self, client):
        """Even with invalid UUID, unauthenticated should get 401 not 404."""
        r = client.post("/api/v1/notifications/not-a-uuid/read")
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────
# 14. Resources list API — no auth required
# ──────────────────────────────────────────────────────────────

class TestResourcesListAPIPublic:

    def test_list_returns_200(self, client):
        """Resources list is public (no @require_auth on list_resources)."""
        r = client.get("/api/v1/resources")
        assert r.status_code == 200

    def test_list_with_pagination_params(self, client):
        r = client.get("/api/v1/resources?page=1&limit=5")
        assert r.status_code == 200

    def test_list_response_has_data_key(self, client):
        import json
        r = client.get("/api/v1/resources")
        body = json.loads(r.get_data(as_text=True))
        assert "data" in body

    def test_list_response_has_meta(self, client):
        import json
        r = client.get("/api/v1/resources?page=1&limit=5")
        body = json.loads(r.get_data(as_text=True))
        assert "meta" in body
        assert "total" in body["meta"]
        assert "page" in body["meta"]


# ──────────────────────────────────────────────────────────────
# 15. Nav — design system compliance
# ──────────────────────────────────────────────────────────────

class TestStudentNavDesign:

    PAGES = [
        "/student/dashboard",
        "/student/courses",
        "/student/resources",
        "/student/notifications",
        "/student/profile",
    ]

    def test_nav_items_present_on_all_pages(self, client):
        for path in self.PAGES:
            body = client.get(path).get_data(as_text=True)
            assert "sidebar-nav" in body or "_nav.html" in body or "nav-item" in body, f"{path} missing nav"

    def test_no_blue_purple_on_any_page(self, client):
        forbidden = ["#6366f1", "#8b5cf6", "#3b82f6", "indigo", "violet", "purple"]
        for path in self.PAGES:
            body = client.get(path).get_data(as_text=True)
            for token in forbidden:
                assert token not in body, f"{path} contains forbidden token '{token}'"

    def test_forest_color_present(self, client):
        """At least one reference to the forest design token per page."""
        for path in self.PAGES:
            body = client.get(path).get_data(as_text=True)
            assert "forest" in body.lower(), f"{path} missing forest palette reference"

    def test_design_system_css_linked(self, client):
        for path in self.PAGES:
            body = client.get(path).get_data(as_text=True)
            assert "design-system.css" in body, f"{path} missing design-system.css"

    def test_api_js_linked(self, client):
        for path in self.PAGES:
            body = client.get(path).get_data(as_text=True)
            assert "api.js" in body, f"{path} missing api.js"
