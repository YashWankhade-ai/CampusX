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
def get_contribution_leaderboard():
    timeframe = request.args.get('timeframe', 'all_time')
    limit = request.args.get('limit', 10, type=int)
    leaders = contribution_service.get_leaderboard(timeframe, limit)
    return success_response(data=leaders)
