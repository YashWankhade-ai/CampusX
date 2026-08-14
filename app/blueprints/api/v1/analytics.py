from flask import Blueprint, request
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
