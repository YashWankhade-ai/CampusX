import os

API_DIR = r"C:\Users\ASUS\.gemini\antigravity\scratch\campusx\app\blueprints\api\v1"

auth_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.auth_service import AuthService
from app.schemas.auth_schemas import RegisterSchema, LoginSchema, ResetPasswordSchema
from app.middleware.auth import require_auth
from marshmallow import ValidationError

auth_bp = Blueprint('auth', __name__)
auth_service = AuthService()

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = RegisterSchema().load(request.json)
        result = auth_service.register(data)
        return success_response(data=result, message="Registration successful", status_code=201)
    except ValidationError as e:
        return error_response(code="VALIDATION_ERROR", message=e.messages, status_code=400)
    except Exception as e:
        return error_response(code="INTERNAL_ERROR", message=str(e), status_code=500)

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = LoginSchema().load(request.json)
        result = auth_service.login(data['email'], data['password'])
        return success_response(data=result, message="Login successful")
    except ValidationError as e:
        return error_response(code="VALIDATION_ERROR", message=e.messages, status_code=400)
    except ValueError as e:
        return error_response(code="AUTH_FAILED", message=str(e), status_code=401)
    except Exception as e:
        return error_response(code="INTERNAL_ERROR", message=str(e), status_code=500)

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    try:
        refresh_token = request.json.get('refresh_token')
        result = auth_service.refresh(refresh_token)
        return success_response(data=result, message="Token refreshed")
    except Exception as e:
        return error_response(code="AUTH_FAILED", message=str(e), status_code=401)

@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    auth_service.logout(request.user.id)
    return success_response(data=None, message="Logout successful")

@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    try:
        otp = request.json.get('otp')
        email = request.json.get('email')
        auth_service.verify_otp(email, otp)
        return success_response(data=None, message="OTP verified")
    except Exception as e:
        return error_response(code="VERIFY_FAILED", message=str(e), status_code=400)

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.json.get('email')
    auth_service.forgot_password(email)
    return success_response(data=None, message="Password reset link sent")

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = ResetPasswordSchema().load(request.json)
        auth_service.reset_password(data['token'], data['new_password'])
        return success_response(data=None, message="Password reset successful")
    except ValidationError as e:
        return error_response(code="VALIDATION_ERROR", message=e.messages, status_code=400)
    except Exception as e:
        return error_response(code="RESET_FAILED", message=str(e), status_code=400)
"""

resources_content = """from flask import Blueprint, request, send_file
from app.utils.response_utils import success_response, error_response
from app.services.resource_service import ResourceService
from app.schemas.resource_schemas import ResourceUploadSchema, ResourceResponseSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role

resources_bp = Blueprint('resources', __name__)
resource_service = ResourceService()

@resources_bp.route('/', methods=['GET'])
@require_auth
def list_resources():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    subject = request.args.get('subject')
    category = request.args.get('category')
    sort_by = request.args.get('sort_by', 'created_at')
    search = request.args.get('search')
    
    data, total = resource_service.get_resources(
        page=page, limit=limit, subject=subject, category=category, sort_by=sort_by, search=search
    )
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=ResourceResponseSchema(many=True).dump(data), meta=meta)

@resources_bp.route('/', methods=['POST'])
@require_auth
@require_role(['contributor', 'admin'])
def upload_resource():
    try:
        data = ResourceUploadSchema().load(request.form)
        file = request.files.get('file')
        result = resource_service.upload(request.user.id, data, file)
        return success_response(data=ResourceResponseSchema().dump(result), message="Resource uploaded", status_code=201)
    except Exception as e:
        return error_response(code="UPLOAD_ERROR", message=str(e), status_code=400)

@resources_bp.route('/<int:resource_id>', methods=['GET'])
@require_auth
def get_resource(resource_id):
    resource = resource_service.get_by_id(resource_id)
    if not resource:
        return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)
    return success_response(data=ResourceResponseSchema().dump(resource))

@resources_bp.route('/<int:resource_id>/download', methods=['GET'])
@require_auth
def download_resource(resource_id):
    try:
        file_path, filename = resource_service.get_download_path(resource_id, request.user.id)
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return error_response(code="DOWNLOAD_ERROR", message=str(e), status_code=400)

@resources_bp.route('/<int:resource_id>/bookmark', methods=['POST'])
@require_auth
def bookmark_resource(resource_id):
    resource_service.toggle_bookmark(resource_id, request.user.id)
    return success_response(data=None, message="Bookmark toggled")

@resources_bp.route('/<int:resource_id>/rate', methods=['POST'])
@require_auth
def rate_resource(resource_id):
    rating = request.json.get('rating')
    resource_service.add_rating(resource_id, request.user.id, rating)
    return success_response(data=None, message="Rating submitted")
"""

search_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.search_service import SearchService

search_bp = Blueprint('search', __name__)
search_service = SearchService()

@search_bp.route('/', methods=['GET'])
def hybrid_search():
    query = request.args.get('query', '')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    filters = request.args.to_dict()
    
    results, total = search_service.perform_hybrid_search(query, filters, page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=results, meta=meta)

@search_bp.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('query', '')
    suggestions = search_service.get_autocomplete(query)
    return success_response(data=suggestions)

@search_bp.route('/trending', methods=['GET'])
def trending():
    results = search_service.get_trending()
    return success_response(data=results)
"""

ai_content = """from flask import Blueprint, request, Response
from app.utils.response_utils import success_response, error_response
from app.services.ai_service import AIService
from app.middleware.auth import require_auth

ai_bp = Blueprint('ai', __name__)
ai_service = AIService()

@ai_bp.route('/chat', methods=['POST'])
@require_auth
def chat():
    prompt = request.json.get('prompt')
    if request.json.get('stream'):
        return Response(ai_service.chat_stream(prompt, request.user.id), mimetype='text/event-stream')
    
    response = ai_service.chat(prompt, request.user.id)
    return success_response(data={"response": response})

@ai_bp.route('/quiz/generate', methods=['POST'])
@require_auth
def generate_quiz():
    topic = request.json.get('topic')
    difficulty = request.json.get('difficulty', 'medium')
    quiz = ai_service.generate_quiz(topic, difficulty)
    return success_response(data=quiz, message="Quiz generated")

@ai_bp.route('/flashcards/generate', methods=['POST'])
@require_auth
def generate_flashcards():
    text = request.json.get('text')
    flashcards = ai_service.generate_flashcards(text)
    return success_response(data=flashcards, message="Flashcards generated")

@ai_bp.route('/summarize', methods=['POST'])
@require_auth
def summarize():
    text = request.json.get('text')
    summary = ai_service.summarize(text)
    return success_response(data={"summary": summary}, message="Summary generated")
"""

users_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.user_service import UserService
from app.schemas.user_schemas import UserResponseSchema, UserUpdateSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role
from marshmallow import ValidationError

users_bp = Blueprint('users', __name__)
user_service = UserService()

@users_bp.route('/me', methods=['GET'])
@require_auth
def get_me():
    user = user_service.get_by_id(request.user.id)
    return success_response(data=UserResponseSchema().dump(user))

@users_bp.route('/me', methods=['PUT'])
@require_auth
def update_me():
    try:
        data = UserUpdateSchema().load(request.json)
        user = user_service.update_profile(request.user.id, data)
        return success_response(data=UserResponseSchema().dump(user), message="Profile updated")
    except ValidationError as e:
        return error_response(code="VALIDATION_ERROR", message=e.messages, status_code=400)

@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    limit = request.args.get('limit', 10, type=int)
    users = user_service.get_leaderboard(limit)
    return success_response(data=UserResponseSchema(many=True).dump(users))

@users_bp.route('/', methods=['GET'])
@require_auth
@require_role(['admin'])
def list_users():
    role = request.args.get('role')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    users, total = user_service.list_users(role, page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=UserResponseSchema(many=True).dump(users), meta=meta)
"""

academic_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.academic_service import AcademicService
from app.schemas.academic_schemas import SubjectSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role

academic_bp = Blueprint('academic', __name__)
academic_service = AcademicService()

@academic_bp.route('/institutions', methods=['GET'])
def get_institutions():
    institutions = academic_service.get_institutions()
    return success_response(data=institutions)

@academic_bp.route('/departments', methods=['GET'])
def get_departments():
    institution_id = request.args.get('institution_id')
    departments = academic_service.get_departments(institution_id)
    return success_response(data=departments)

@academic_bp.route('/subjects', methods=['GET'])
def get_subjects():
    department_id = request.args.get('department_id')
    subjects = academic_service.get_subjects(department_id)
    return success_response(data=SubjectSchema(many=True).dump(subjects))

@academic_bp.route('/subjects', methods=['POST'])
@require_auth
@require_role(['admin'])
def create_subject():
    data = request.json
    subject = academic_service.create_subject(data)
    return success_response(data=SubjectSchema().dump(subject), message="Subject created", status_code=201)
"""

notifications_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.notification_service import NotificationService
from app.middleware.auth import require_auth

notifications_bp = Blueprint('notifications', __name__)
notification_service = NotificationService()

@notifications_bp.route('/', methods=['GET'])
@require_auth
def get_notifications():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    notifications, total = notification_service.get_user_notifications(request.user.id, page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=notifications, meta=meta)

@notifications_bp.route('/read-all', methods=['POST'])
@require_auth
def mark_all_read():
    notification_service.mark_all_as_read(request.user.id)
    return success_response(data=None, message="All notifications marked as read")

@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@require_auth
def mark_read(notification_id):
    notification_service.mark_as_read(notification_id, request.user.id)
    return success_response(data=None, message="Notification marked as read")
"""

analytics_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.analytics_service import AnalyticsService
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role

analytics_bp = Blueprint('analytics', __name__)
analytics_service = AnalyticsService()

@analytics_bp.route('/dashboard', methods=['GET'])
@require_auth
def user_dashboard():
    stats = analytics_service.get_user_dashboard(request.user.id)
    return success_response(data=stats)

@analytics_bp.route('/overview', methods=['GET'])
@require_auth
@require_role(['admin'])
def platform_overview():
    stats = analytics_service.get_platform_overview()
    return success_response(data=stats)
"""

qr_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.qr_service import QRService
from app.middleware.auth import require_auth

qr_bp = Blueprint('qr', __name__)
qr_service = QRService()

@qr_bp.route('/generate', methods=['POST'])
@require_auth
def generate_qr():
    data = request.json.get('data')
    purpose = request.json.get('purpose', 'general')
    qr_code = qr_service.generate_code(data, purpose, request.user.id)
    return success_response(data=qr_code, message="QR code generated", status_code=201)

@qr_bp.route('/scan', methods=['POST'])
@require_auth
def scan_qr():
    qr_data = request.json.get('qr_data')
    result = qr_service.process_scan(qr_data, request.user.id)
    return success_response(data=result, message="QR scanned successfully")
"""

approvals_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.approval_service import ApprovalService
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role

approvals_bp = Blueprint('approvals', __name__)
approval_service = ApprovalService()

@approvals_bp.route('/pending', methods=['GET'])
@require_auth
@require_role(['admin', 'moderator'])
def get_pending_approvals():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    approvals, total = approval_service.get_pending(page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=approvals, meta=meta)

@approvals_bp.route('/<int:item_id>/approve', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def approve_item(item_id):
    result = approval_service.approve(item_id, request.user.id)
    return success_response(data=result, message="Item approved")

@approvals_bp.route('/<int:item_id>/reject', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def reject_item(item_id):
    reason = request.json.get('reason')
    result = approval_service.reject(item_id, request.user.id, reason)
    return success_response(data=result, message="Item rejected")

@approvals_bp.route('/<int:item_id>/request-changes', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def request_changes(item_id):
    feedback = request.json.get('feedback')
    result = approval_service.request_changes(item_id, request.user.id, feedback)
    return success_response(data=result, message="Changes requested")
"""

contributions_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.contribution_service import ContributionService
from app.middleware.auth import require_auth

contributions_bp = Blueprint('contributions', __name__)
contribution_service = ContributionService()

@contributions_bp.route('/score', methods=['GET'])
@require_auth
def get_score():
    score = contribution_service.get_user_score(request.user.id)
    return success_response(data={"score": score})

@contributions_bp.route('/badges', methods=['GET'])
@require_auth
def get_badges():
    badges = contribution_service.get_user_badges(request.user.id)
    return success_response(data=badges)

@contributions_bp.route('/leaderboard', methods=['GET'])
def get_contribution_leaderboard():
    timeframe = request.args.get('timeframe', 'all_time')
    limit = request.args.get('limit', 10, type=int)
    leaders = contribution_service.get_leaderboard(timeframe, limit)
    return success_response(data=leaders)
"""

settings_content = """from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.setting_service import SettingService
from app.middleware.auth import require_auth
from app.schemas.setting_schemas import SettingsSchema

settings_bp = Blueprint('settings', __name__)
setting_service = SettingService()

@settings_bp.route('/', methods=['GET'])
@require_auth
def get_settings():
    settings = setting_service.get_user_settings(request.user.id)
    return success_response(data=SettingsSchema().dump(settings))

@settings_bp.route('/', methods=['PUT'])
@require_auth
def update_settings():
    data = SettingsSchema().load(request.json)
    settings = setting_service.update_user_settings(request.user.id, data)
    return success_response(data=SettingsSchema().dump(settings), message="Settings updated")
"""

files_to_write = {
    'auth.py': auth_content,
    'resources.py': resources_content,
    'search.py': search_content,
    'ai.py': ai_content,
    'users.py': users_content,
    'academic.py': academic_content,
    'notifications.py': notifications_content,
    'analytics.py': analytics_content,
    'qr.py': qr_content,
    'approvals.py': approvals_content,
    'contributions.py': contributions_content,
    'settings.py': settings_content,
}

for filename, content in files_to_write.items():
    path = os.path.join(API_DIR, filename)
    with open(path, "w") as f:
        f.write(content)

print("DONE")
