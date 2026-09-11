from flask import Blueprint

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

from .auth import auth_bp
from .resources import resources_bp
from .search import search_bp
from .ai import ai_bp
from .users import users_bp
from .academic import academic_bp
from .notifications import notifications_bp
from .analytics import analytics_bp
from .qr import qr_bp
from .approvals import approvals_bp
from .contributions import contributions_bp
from .settings import settings_bp
from .admin import admin_bp
from .student import student_bp
from .faculty import faculty_bp

api_v1_bp.register_blueprint(auth_bp, url_prefix="/auth")
api_v1_bp.register_blueprint(resources_bp, url_prefix="/resources")
api_v1_bp.register_blueprint(search_bp, url_prefix="/search")
api_v1_bp.register_blueprint(ai_bp, url_prefix="/ai")
api_v1_bp.register_blueprint(users_bp, url_prefix="/users")
api_v1_bp.register_blueprint(academic_bp, url_prefix="/academic")
api_v1_bp.register_blueprint(notifications_bp, url_prefix="/notifications")
api_v1_bp.register_blueprint(analytics_bp, url_prefix="/analytics")
api_v1_bp.register_blueprint(qr_bp, url_prefix="/qr")
api_v1_bp.register_blueprint(approvals_bp, url_prefix="/approvals")
api_v1_bp.register_blueprint(contributions_bp, url_prefix="/contributions")
api_v1_bp.register_blueprint(settings_bp, url_prefix="/settings")
api_v1_bp.register_blueprint(admin_bp, url_prefix="/admin")
api_v1_bp.register_blueprint(student_bp, url_prefix="/student")
api_v1_bp.register_blueprint(faculty_bp, url_prefix="/faculty")
