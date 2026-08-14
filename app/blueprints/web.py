from flask import Blueprint, render_template, request, redirect, url_for

web_bp = Blueprint("web", __name__)

# Base / Landing
@web_bp.route("/")
def index():
    return render_template("student/dashboard.html")

# Auth Views
@web_bp.route("/login")
def login():
    return render_template("auth/login.html")

@web_bp.route("/register")
def register():
    return render_template("auth/register.html")

# Student Views
@web_bp.route("/student/dashboard")
def student_dashboard():
    return render_template("student/dashboard.html")

@web_bp.route("/student/library")
def student_library():
    return render_template("student/library.html")

@web_bp.route("/student/library/<resource_id>")
def student_library_detail(resource_id):
    return render_template("student/detail.html", resource_id=resource_id)

@web_bp.route("/student/ai-chat")
def student_ai_chat():
    return render_template("student/ai_chat.html")

@web_bp.route("/student/quiz")
def student_quiz():
    return render_template("student/quiz.html")

@web_bp.route("/student/flashcards")
def student_flashcards():
    return render_template("student/flashcards.html")

@web_bp.route("/student/search")
def student_search():
    query = request.args.get("q", "")
    return render_template("student/search.html", query=query)

@web_bp.route("/student/bookmarks")
def student_bookmarks():
    return render_template("student/bookmarks.html")

@web_bp.route("/student/leaderboard")
def student_leaderboard():
    return render_template("student/leaderboard.html")

@web_bp.route("/student/profile")
def student_profile():
    return render_template("student/profile.html")

@web_bp.route("/student/notifications")
def student_notifications():
    return render_template("student/notifications.html")

@web_bp.route("/student/qr")
def student_qr():
    return render_template("student/qr.html")

# Faculty Views
@web_bp.route("/faculty/dashboard")
def faculty_dashboard():
    return render_template("faculty/dashboard.html")

@web_bp.route("/faculty/upload")
def faculty_upload():
    return render_template("faculty/upload.html")

@web_bp.route("/faculty/my-uploads")
def faculty_my_uploads():
    return render_template("faculty/my_uploads.html")

@web_bp.route("/faculty/approvals")
def faculty_approvals():
    return render_template("faculty/approvals.html")

@web_bp.route("/faculty/subjects")
def faculty_subjects():
    return render_template("faculty/subjects.html")

@web_bp.route("/faculty/analytics")
def faculty_analytics():
    return render_template("faculty/analytics.html")

# Admin Views
@web_bp.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin/dashboard.html")

@web_bp.route("/admin/institutions")
def admin_institutions():
    return render_template("admin/institutions.html")

@web_bp.route("/admin/users")
def admin_users():
    return render_template("admin/users.html")

@web_bp.route("/admin/approval-queue")
def admin_approval_queue():
    return render_template("admin/approval_queue.html")

@web_bp.route("/admin/analytics")
def admin_analytics():
    return render_template("admin/analytics.html")

@web_bp.route("/admin/departments")
def admin_departments():
    return render_template("admin/departments.html")

@web_bp.route("/admin/roles")
def admin_roles():
    return render_template("admin/roles.html")

@web_bp.route("/admin/settings")
def admin_settings():
    return render_template("admin/settings.html")

@web_bp.route("/admin/audit-log")
def admin_audit_log():
    return render_template("admin/audit_log.html")
