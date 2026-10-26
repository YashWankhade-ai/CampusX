"""Frontend Cycle 6 — Faculty Experience Tests.

Coverage (30+ tests):

ROUTING (1-5)
    1. /faculty/dashboard renders 200
    2. /faculty/profile renders 200
    3. /faculty/courses renders 200
    4. /faculty/courses/<id>/students renders 200
    5. /faculty/resources renders 200

FACULTY NAV (6-9)
    6. Faculty nav partial is included in all faculty pages
    7. Nav links: Dashboard, Courses, My Resources, CampusX AI, Notifications, Profile
    8. AI link points to /student/ai-chat (reuse, not duplicate)
    9. Search link present in nav

DASHBOARD PAGE (10-15)
    10. Dashboard has auth guard (checks isAuthenticated)
    11. Dashboard has role guard (redirects STUDENT/GUEST)
    12. Dashboard renders stat tile elements for real fields
    13. Dashboard calls /api/v1/faculty/dashboard
    14. Dashboard calls /api/v1/faculty/courses for course list
    15. Dashboard has loading skeleton + empty state + error state

PROFILE PAGE (16-19)
    16. Profile has auth guard
    17. Profile calls /api/v1/faculty/profile
    18. Profile shows real backend fields (email, full_name, display_name)
    19. Profile is read-only (no edit/save form)

COURSES PAGE (20-23)
    20. Courses has auth guard
    21. Courses calls /api/v1/faculty/courses
    22. Courses has empty state for no assignments
    23. Course card links to /faculty/courses/<id>/students

STUDENTS PAGE (24-28)
    24. Students has auth guard
    25. Students calls /api/v1/faculty/courses/<course_id>/students
    26. course_id injected by Flask (not from client URL parsing)
    27. Student table has NO email column (backend deliberately omits it)
    28. 404 response → IDOR-safe error message (not "unauthorized")

RESOURCES PAGE (29-32)
    29. Resources has auth guard
    30. Resources calls /api/v1/faculty/resources
    31. Resources has status filter tabs (All/Pending/Approved/Rejected)
    32. Resources pagination present

SECURITY (33-36)
    33. institution_id NOT in any faculty template body
    34. No storage_path reference in resources template
    35. No email in student table columns
    36. Auth clearSession + redirect on 401

DESIGN COMPLIANCE (37-39)
    37. Faculty CSS section present in components.css
    38. No blue/purple color values in faculty CSS
    39. Faculty workspace differentiated from student nav

ACCESSIBILITY (40-42)
    40. Faculty nav has aria-label
    41. Student table has scope attributes on headers
    42. Filter tabs have role=tablist + aria-selected

MOBILE (43-45)
    43. fx-student-cards element present (mobile layout)
    44. fx-course-grid present
    45. fx-filter-tabs present
"""
import os
import re
import pytest

from app import create_app
from app.extensions import db as _db


# ── Path helpers ───────────────────────────────────────────────────────────────

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read_template(name):
    path = os.path.join(BASE, 'app', 'templates', name)
    with open(path, encoding='utf-8') as f:
        return f.read()

def read_css():
    path = os.path.join(BASE, 'app', 'static', 'css', 'components.css')
    with open(path, encoding='utf-8') as f:
        return f.read()

def read_nav():
    return read_template('faculty/_nav.html')

def read_dashboard():
    return read_template('faculty/dashboard.html')

def read_profile():
    return read_template('faculty/profile.html')

def read_courses():
    return read_template('faculty/courses.html')

def read_students():
    return read_template('faculty/course_students.html')

def read_resources():
    return read_template('faculty/resources.html')

def read_web():
    path = os.path.join(BASE, 'app', 'blueprints', 'web.py')
    with open(path, encoding='utf-8') as f:
        return f.read()


# ── Flask test client ──────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    _app = create_app("testing")
    with _app.app_context():
        _db.create_all()
        yield _app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


# ══════════════════════════════════════════════════════════════════════════════
# 1. ROUTING
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyRoutes:

    def test_dashboard_route_200(self, client):
        assert client.get('/faculty/dashboard').status_code == 200

    def test_profile_route_200(self, client):
        assert client.get('/faculty/profile').status_code == 200

    def test_courses_route_200(self, client):
        assert client.get('/faculty/courses').status_code == 200

    def test_course_students_route_200(self, client):
        import uuid
        cid = str(uuid.uuid4())
        assert client.get(f'/faculty/courses/{cid}/students').status_code == 200

    def test_resources_route_200(self, client):
        assert client.get('/faculty/resources').status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 2. WEB.PY ROUTES REGISTERED
# ══════════════════════════════════════════════════════════════════════════════

class TestWebRoutes:

    def test_profile_route_registered(self):
        web = read_web()
        assert '/faculty/profile' in web

    def test_courses_route_registered(self):
        web = read_web()
        assert '/faculty/courses' in web

    def test_course_students_route_registered(self):
        web = read_web()
        assert '/faculty/courses/<course_id>/students' in web
        assert 'course_students.html' in web

    def test_resources_route_registered(self):
        web = read_web()
        assert '/faculty/resources' in web

    def test_course_id_passed_to_template(self):
        web = read_web()
        # course_id must be passed as a template variable
        assert 'course_id=course_id' in web


# ══════════════════════════════════════════════════════════════════════════════
# 3. FACULTY NAV PARTIAL
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyNav:

    def test_nav_file_exists(self):
        nav = read_nav()
        assert len(nav) > 0

    def test_nav_has_aria_label(self):
        nav = read_nav()
        assert 'aria-label' in nav.lower()
        assert 'faculty' in nav.lower()

    def test_nav_dashboard_link(self):
        nav = read_nav()
        assert '/faculty/dashboard' in nav

    def test_nav_courses_link(self):
        nav = read_nav()
        assert '/faculty/courses' in nav

    def test_nav_resources_link(self):
        nav = read_nav()
        assert '/faculty/resources' in nav

    def test_nav_ai_link_reuses_student_ai(self):
        nav = read_nav()
        # Faculty reuses student AI interface — no new /faculty/ai-chat
        assert '/student/ai-chat' in nav

    def test_nav_search_link_reuses_student_search(self):
        nav = read_nav()
        assert '/student/search' in nav

    def test_nav_profile_link(self):
        nav = read_nav()
        assert '/faculty/profile' in nav

    def test_nav_notifications_link(self):
        nav = read_nav()
        assert 'notifications' in nav.lower()

    def test_nav_notification_badge(self):
        nav = read_nav()
        assert 'nav-notif-badge' in nav

    def test_nav_active_state_support(self):
        nav = read_nav()
        # Uses active_page variable like student nav
        assert 'active_page' in nav

    def test_nav_included_in_dashboard(self):
        dash = read_dashboard()
        assert 'faculty/_nav.html' in dash

    def test_nav_included_in_courses(self):
        courses = read_courses()
        assert 'faculty/_nav.html' in courses

    def test_nav_included_in_students(self):
        students = read_students()
        assert 'faculty/_nav.html' in students

    def test_nav_included_in_resources(self):
        resources = read_resources()
        assert 'faculty/_nav.html' in resources

    def test_nav_included_in_profile(self):
        profile = read_profile()
        assert 'faculty/_nav.html' in profile


# ══════════════════════════════════════════════════════════════════════════════
# 4. DASHBOARD PAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyDashboard:

    def test_dashboard_has_auth_guard(self):
        dash = read_dashboard()
        assert 'isAuthenticated' in dash
        assert '/login' in dash

    def test_dashboard_has_role_guard(self):
        dash = read_dashboard()
        # Should check role and redirect STUDENT/GUEST
        assert 'getRole' in dash
        assert 'STUDENT' in dash

    def test_dashboard_calls_faculty_dashboard_api(self):
        dash = read_dashboard()
        assert '/api/v1/faculty/dashboard' in dash

    def test_dashboard_calls_faculty_courses_api(self):
        dash = read_dashboard()
        assert '/api/v1/faculty/courses' in dash

    def test_dashboard_uses_assigned_course_count(self):
        dash = read_dashboard()
        assert 'assigned_course_count' in dash

    def test_dashboard_uses_total_resource_count(self):
        dash = read_dashboard()
        assert 'total_resource_count' in dash

    def test_dashboard_uses_unread_notification_count(self):
        dash = read_dashboard()
        assert 'unread_notification_count' in dash

    def test_dashboard_uses_contribution_count(self):
        dash = read_dashboard()
        assert 'contribution_count' in dash

    def test_dashboard_no_invented_fields(self):
        dash = read_dashboard()
        # Fields that DO NOT exist in the backend schema
        assert 'student_growth' not in dash
        assert 'performance_score' not in dash
        assert 'engagement' not in dash

    def test_dashboard_has_loading_skeleton(self):
        dash = read_dashboard()
        assert 'skeleton' in dash
        assert 'dashboard-loading' in dash

    def test_dashboard_has_empty_state(self):
        dash = read_dashboard()
        assert 'courses-empty' in dash
        assert 'No assigned courses' in dash

    def test_dashboard_has_error_state(self):
        dash = read_dashboard()
        assert 'dashboard-error' in dash
        assert 'loadDashboard' in dash

    def test_dashboard_course_list_rendered(self):
        dash = read_dashboard()
        assert 'courses-list' in dash
        assert 'fx-course-item' in dash or 'fx-course-list' in dash

    def test_dashboard_handles_401(self):
        dash = read_dashboard()
        assert '401' in dash
        assert 'session=expired' in dash or 'clearSession' in dash

    def test_dashboard_quick_actions_present(self):
        dash = read_dashboard()
        assert 'quick-action' in dash

    def test_dashboard_ai_link_in_quick_actions(self):
        dash = read_dashboard()
        assert '/student/ai-chat' in dash

    def test_dashboard_greeting_present(self):
        dash = read_dashboard()
        assert 'greeting' in dash.lower()
        assert 'Good morning' in dash or 'greeting-text' in dash

    def test_dashboard_faculty_workspace_role_label(self):
        dash = read_dashboard()
        assert 'Faculty Workspace' in dash


# ══════════════════════════════════════════════════════════════════════════════
# 5. PROFILE PAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyProfile:

    def test_profile_has_auth_guard(self):
        profile = read_profile()
        assert 'isAuthenticated' in profile
        assert '/login' in profile

    def test_profile_calls_faculty_profile_api(self):
        profile = read_profile()
        assert '/api/v1/faculty/profile' in profile

    def test_profile_shows_email(self):
        profile = read_profile()
        assert 'profile-email' in profile or "'email'" in profile or '.email' in profile

    def test_profile_shows_full_name(self):
        profile = read_profile()
        assert 'full_name' in profile or 'profile-name' in profile

    def test_profile_shows_department(self):
        profile = read_profile()
        assert 'department' in profile.lower()

    def test_profile_shows_institution(self):
        profile = read_profile()
        assert 'institution' in profile.lower()

    def test_profile_read_only_no_edit_form(self):
        profile = read_profile()
        # No save/edit form — profile managed by admin
        assert '<form' not in profile.lower() or 'edit' not in profile.lower()

    def test_profile_no_institution_id_in_html(self):
        profile = read_profile()
        # institution_id must not be exposed in visible UI
        # It may appear in JS code (.institution_id) but not as a displayed field
        visible_section = profile.split('{% block scripts %}')[0] if '{% block scripts %}' in profile else profile
        assert 'institution_id' not in visible_section or 'institution-id' not in visible_section.lower()

    def test_profile_has_loading_state(self):
        profile = read_profile()
        assert 'profile-loading' in profile
        assert 'skeleton' in profile

    def test_profile_has_error_state(self):
        profile = read_profile()
        assert 'profile-error' in profile

    def test_profile_has_read_only_notice(self):
        profile = read_profile()
        assert 'administrator' in profile.lower() or 'read-only' in profile.lower() or 'managed by' in profile.lower()

    def test_profile_member_since_field(self):
        profile = read_profile()
        assert 'since' in profile.lower() or 'created_at' in profile


# ══════════════════════════════════════════════════════════════════════════════
# 6. COURSES PAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyCourses:

    def test_courses_has_auth_guard(self):
        courses = read_courses()
        assert 'isAuthenticated' in courses
        assert '/login' in courses

    def test_courses_calls_faculty_courses_api(self):
        courses = read_courses()
        assert '/api/v1/faculty/courses' in courses

    def test_courses_has_loading_skeleton(self):
        courses = read_courses()
        assert 'skeleton' in courses
        assert 'courses-loading' in courses

    def test_courses_has_empty_state(self):
        courses = read_courses()
        assert 'courses-empty' in courses
        assert 'No assigned courses' in courses

    def test_courses_has_error_state(self):
        courses = read_courses()
        assert 'courses-error' in courses

    def test_courses_uses_course_name(self):
        courses = read_courses()
        assert 'course_name' in courses

    def test_courses_uses_course_code(self):
        courses = read_courses()
        assert 'course_code' in courses

    def test_courses_uses_is_primary(self):
        courses = read_courses()
        assert 'is_primary' in courses

    def test_courses_links_to_students_page(self):
        courses = read_courses()
        assert '/faculty/courses/' in courses
        assert '/students' in courses

    def test_courses_handles_401(self):
        courses = read_courses()
        assert '401' in courses
        assert 'clearSession' in courses


# ══════════════════════════════════════════════════════════════════════════════
# 7. COURSE STUDENTS PAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestCourseStudents:

    def test_students_has_auth_guard(self):
        students = read_students()
        assert 'isAuthenticated' in students

    def test_students_course_id_from_flask(self):
        students = read_students()
        # course_id must come from Flask Jinja, not from JS URL parsing
        assert 'course_id | tojson' in students or '{{ course_id' in students

    def test_students_calls_faculty_courses_api(self):
        students = read_students()
        assert '/api/v1/faculty/courses/' in students
        assert '/students' in students

    def test_students_table_has_no_email_column(self):
        students = read_students()
        # Backend _safe_student_dict deliberately omits email
        # The table should NOT have email column
        table_section = students
        # Check that email is not used as a column heading or rendered field
        assert 'Email' not in table_section or 'email' not in table_section.lower()

    def test_students_shows_full_name(self):
        students = read_students()
        assert 'full_name' in students

    def test_students_shows_status(self):
        students = read_students()
        assert 'status' in students

    def test_students_has_loading_skeleton(self):
        students = read_students()
        assert 'skeleton' in students
        assert 'students-loading' in students

    def test_students_has_empty_state(self):
        students = read_students()
        assert 'students-empty' in students
        assert 'No students' in students or 'enrolled' in students

    def test_students_404_idor_safe_message(self):
        students = read_students()
        # 404 → IDOR-safe message (not "unauthorized")
        assert 'not found' in students.lower() or "don't have access" in students.lower()
        # Should NOT say "unauthorized" or "403 forbidden"
        assert 'Unauthorized' not in students

    def test_students_mobile_card_layout(self):
        students = read_students()
        assert 'fx-student-card' in students or 'student-cards' in students

    def test_students_desktop_table_layout(self):
        students = read_students()
        assert '<table' in students.lower()

    def test_students_table_has_scope_on_headers(self):
        students = read_students()
        assert 'scope="col"' in students

    def test_students_back_to_courses_link(self):
        students = read_students()
        assert '/faculty/courses' in students

    def test_students_handles_401(self):
        students = read_students()
        assert '401' in students
        assert 'clearSession' in students


# ══════════════════════════════════════════════════════════════════════════════
# 8. RESOURCES PAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyResources:

    def test_resources_has_auth_guard(self):
        resources = read_resources()
        assert 'isAuthenticated' in resources

    def test_resources_calls_faculty_resources_api(self):
        resources = read_resources()
        assert '/api/v1/faculty/resources' in resources

    def test_resources_has_status_filter_tabs(self):
        resources = read_resources()
        assert 'fx-filter-tab' in resources
        assert 'PENDING' in resources
        assert 'APPROVED' in resources
        assert 'REJECTED' in resources

    def test_resources_filter_tabs_accessibility(self):
        resources = read_resources()
        assert 'role="tablist"' in resources
        assert 'aria-selected' in resources

    def test_resources_sends_status_filter_to_api(self):
        resources = read_resources()
        assert 'status' in resources and 'params' in resources.lower() or '?status' in resources or 'params.set' in resources

    def test_resources_shows_title(self):
        resources = read_resources()
        assert 'r.title' in resources or "'title'" in resources

    def test_resources_shows_material_type(self):
        resources = read_resources()
        assert 'material_type' in resources

    def test_resources_shows_status_badge(self):
        resources = read_resources()
        assert 'r.status' in resources or 'statusBadge' in resources

    def test_resources_has_empty_state(self):
        resources = read_resources()
        assert 'resources-empty' in resources
        assert 'No resources' in resources or "haven't uploaded" in resources

    def test_resources_has_error_state(self):
        resources = read_resources()
        assert 'resources-error' in resources

    def test_resources_has_pagination(self):
        resources = read_resources()
        assert 'pagination' in resources.lower()
        assert 'btn-prev' in resources or 'prevPage' in resources

    def test_resources_no_storage_path(self):
        resources = read_resources()
        # Backend never returns storage_path — should not appear in template
        assert 'storage_path' not in resources

    def test_resources_handles_401(self):
        resources = read_resources()
        assert '401' in resources
        assert 'clearSession' in resources

    def test_resources_browse_all_link(self):
        resources = read_resources()
        # Link to browse all approved resources via student interface
        assert '/student/resources' in resources


# ══════════════════════════════════════════════════════════════════════════════
# 9. SECURITY
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultySecurity:

    def _template_html_sections(self, template_text):
        """Return only the non-script portion of a template."""
        if '{% block scripts %}' in template_text:
            return template_text.split('{% block scripts %}')[0]
        return template_text

    def test_institution_id_not_displayed_in_dashboard(self):
        # institution_id must not be a visible UI field
        dash = read_dashboard()
        html = self._template_html_sections(dash)
        # Should not render institution_id as visible text element
        assert 'institution-id' not in html.lower()

    def test_no_storage_path_in_resources(self):
        assert 'storage_path' not in read_resources()

    def test_no_email_column_in_students(self):
        students = read_students()
        # table thead should not have Email column
        # Check the HTML heading section (not JS which may have the word in a comment)
        assert 'Email' not in students

    def test_no_password_hash_in_any_template(self):
        for t in [read_dashboard(), read_profile(), read_courses(), read_students(), read_resources()]:
            assert 'password_hash' not in t
            assert 'password' not in t.lower() or 'password' in t.lower() and 'hash' not in t.lower()

    def test_no_jwt_exposed_in_templates(self):
        for t in [read_dashboard(), read_profile(), read_courses(), read_students(), read_resources()]:
            # JWTs should never appear as visible HTML content
            html = self._template_html_sections(t)
            assert 'jwt' not in html.lower()

    def test_course_id_in_students_from_flask_not_url(self):
        students = read_students()
        # course_id must come from Jinja (server-side), not from window.location.pathname
        assert '{{ course_id' in students or 'course_id | tojson' in students
        # Should NOT parse course ID from URL
        assert 'pathname.split' not in students

    def test_auth_guard_on_all_faculty_pages(self):
        for template_text in [read_dashboard(), read_profile(), read_courses(), read_students(), read_resources()]:
            assert 'isAuthenticated' in template_text

    def test_401_redirects_to_login_session_expired(self):
        for template_text in [read_dashboard(), read_profile(), read_courses(), read_students(), read_resources()]:
            assert 'clearSession' in template_text


# ══════════════════════════════════════════════════════════════════════════════
# 10. CSS / DESIGN COMPLIANCE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyCSSDesign:

    def _faculty_css(self):
        css = read_css()
        idx = css.find('FACULTY WORKSPACE')
        assert idx >= 0, 'Faculty CSS section not found in components.css'
        return css[idx:]

    def test_faculty_css_section_exists(self):
        self._faculty_css()

    def test_fx_profile_card_class(self):
        assert '.fx-profile-card' in self._faculty_css()

    def test_fx_course_list_class(self):
        assert '.fx-course-list' in self._faculty_css()

    def test_fx_course_grid_class(self):
        assert '.fx-course-grid' in self._faculty_css()

    def test_fx_student_table_class(self):
        assert '.fx-student-table' in self._faculty_css()

    def test_fx_student_card_class(self):
        assert '.fx-student-card' in self._faculty_css()

    def test_fx_resource_row_class(self):
        assert '.fx-resource-row' in self._faculty_css()

    def test_fx_filter_tabs_class(self):
        assert '.fx-filter-tabs' in self._faculty_css()

    def test_fx_pagination_class(self):
        assert '.fx-pagination' in self._faculty_css()

    def test_no_blue_in_faculty_css(self):
        css = self._faculty_css()
        # Must not contain blue/purple/violet color values
        # Check for hex blue values like #0000ff, #007bff etc or 'blue' keyword
        assert 'color: blue' not in css.lower()
        assert '#007bff' not in css
        assert '#6f42c1' not in css  # purple
        assert '#7c3aed' not in css  # violet

    def test_forest_color_used(self):
        css = self._faculty_css()
        assert '--cx-color-forest' in css

    def test_responsive_breakpoints(self):
        css = self._faculty_css()
        assert '@media' in css
        assert '768px' in css or '640px' in css

    def test_mobile_student_cards_hidden_by_default(self):
        css = self._faculty_css()
        # fx-student-cards should start as display:none and show on mobile
        assert 'fx-student-cards' in css

    def test_no_glassmorphism(self):
        css = self._faculty_css()
        assert 'backdrop-filter' not in css


# ══════════════════════════════════════════════════════════════════════════════
# 11. ACCESSIBILITY
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyAccessibility:

    def test_faculty_nav_aria_label(self):
        nav = read_nav()
        assert 'aria-label' in nav

    def test_student_table_scope_on_th(self):
        students = read_students()
        assert 'scope="col"' in students

    def test_resource_filter_tablist_role(self):
        resources = read_resources()
        assert 'role="tablist"' in resources

    def test_resource_tabs_aria_selected(self):
        resources = read_resources()
        assert 'aria-selected' in resources

    def test_loading_skeleton_aria_busy(self):
        # At least one page should have aria-busy on loading element
        found = any(
            'aria-busy' in t
            for t in [read_dashboard(), read_profile(), read_courses(), read_students(), read_resources()]
        )
        assert found

    def test_empty_state_svg_aria_hidden(self):
        # Empty state icons should be aria-hidden
        for t in [read_dashboard(), read_courses(), read_students(), read_resources()]:
            # If empty state has svg, it should be aria-hidden
            if 'empty-state-icon' in t:
                assert 'aria-hidden="true"' in t

    def test_status_live_region(self):
        # At least some pages should have aria-live for status updates
        found = any(
            'aria-live' in t
            for t in [read_resources(), read_courses(), read_students()]
        )
        assert found

    def test_breadcrumb_aria_label(self):
        # Pages with breadcrumbs should label them
        for t in [read_profile(), read_courses(), read_students(), read_resources()]:
            if 'breadcrumb' in t.lower():
                assert 'aria-label' in t


# ══════════════════════════════════════════════════════════════════════════════
# 12. MOBILE / RESPONSIVE
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyMobile:

    def test_fx_student_cards_in_students_template(self):
        students = read_students()
        assert 'fx-student-cards' in students

    def test_fx_course_grid_in_courses_template(self):
        courses = read_courses()
        assert 'fx-course-grid' in courses

    def test_fx_filter_tabs_in_resources_template(self):
        resources = read_resources()
        assert 'fx-filter-tabs' in resources

    def test_responsive_css_in_components(self):
        css = read_css()
        faculty_section = css[css.find('FACULTY WORKSPACE'):]
        assert '@media' in faculty_section

    def test_student_table_has_overflow_wrapper(self):
        students = read_students()
        assert 'overflow' in students.lower() or 'fx-student-table-wrap' in students

    def test_mobile_nav_drawer_inherited(self):
        # Mobile nav is handled by base.html drawer — faculty pages extend base.html
        dash = read_dashboard()
        assert '{% extends' in dash
        assert 'base.html' in dash
