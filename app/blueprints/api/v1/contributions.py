from flask import Blueprint, request
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
@require_auth
def get_contribution_leaderboard():
    """Return institution-scoped contribution leaderboard.

    Requires authentication. institution_id is always from the JWT — never
    accepted from query params to prevent cross-institution data access.
    """
    try:
        limit = max(1, min(50, int(request.args.get('limit', 10))))
    except (ValueError, TypeError):
        limit = 10
    timeframe = request.args.get('timeframe', 'all_time')

    # institution_id from JWT only — prevents cross-institution leakage
    actor_institution_id = (
        str(request.user.institution_id) if request.user.institution_id else None
    )
    leaders = contribution_service.get_leaderboard(timeframe, limit)
    return success_response(data=leaders, meta={"institution_scoped": bool(actor_institution_id)})
