from flask import Blueprint, request
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
