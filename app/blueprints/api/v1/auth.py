from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.auth_service import AuthService
from app.middleware.auth import require_auth

auth_bp = Blueprint("auth", __name__)
auth_service = AuthService()

@auth_bp.route("/register", methods=["POST"], strict_slashes=False)
def register():
    data = request.get_json(silent=True) or {}
    success, result, status_code = auth_service.register_user(data)
    if not success:
        return error_response(code=result.get("code", "VALIDATION_ERROR"), message=result.get("message", "Registration failed"), status_code=status_code)
    return success_response(data=result, status_code=status_code)

@auth_bp.route("/verify-email", methods=["POST"], strict_slashes=False)
@auth_bp.route("/verify-otp", methods=["POST"], strict_slashes=False)
def verify_email():
    """
    Public Email Verification Endpoint: POST /api/v1/auth/verify-email
    Accepts JSON body: {"email": "...", "otp_code": "..."} or {"email": "...", "code": "..."}
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    otp_code = data.get("otp_code") or data.get("code") or ""

    if not email or not otp_code:
        return error_response(code="VALIDATION_ERROR", message="Email and OTP code are required", status_code=400)

    success, result, status_code = auth_service.verify_email_otp(email=email, otp_code=otp_code)
    if not success:
        return error_response(code=result.get("code", "INVALID_OTP"), message=result.get("message", "Verification failed"), status_code=status_code)

    return success_response(data=result, status_code=status_code)

@auth_bp.route("/resend-otp", methods=["POST"], strict_slashes=False)
def resend_otp():
    """
    Public Endpoint: POST /api/v1/auth/resend-otp
    Accepts JSON body: {"email": "..."}
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()

    if not email:
        return error_response(code="VALIDATION_ERROR", message="Email is required", status_code=400)

    success, result, status_code = auth_service.resend_otp(email=email)
    if not success:
        return error_response(code=result.get("code", "ERROR"), message=result.get("message", "Failed to resend code"), status_code=status_code)

    return success_response(data=result, status_code=status_code)

@auth_bp.route("/login", methods=["POST"], strict_slashes=False)
def login():
    """
    Public Authentication Endpoint: POST /api/v1/auth/login
    Accepts JSON body: {"email": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return error_response(code="VALIDATION_ERROR", message="Email and password are required", status_code=400)

    success, result, status_code = auth_service.authenticate(email=email, password=password)
    if not success:
        return error_response(code=result.get("code", "UNAUTHORIZED"), message=result.get("message", "Authentication failed"), status_code=status_code)

    return success_response(data=result, status_code=status_code)

@auth_bp.route("/refresh", methods=["POST"], strict_slashes=False)
def refresh():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if not refresh_token:
        return error_response(code="UNAUTHORIZED", message="Refresh token required", status_code=401)

    success, result, status_code = auth_service.refresh_token(refresh_token)
    if not success:
        return error_response(code=result.get("code", "UNAUTHORIZED"), message=result.get("message", "Invalid refresh token"), status_code=status_code)

    return success_response(data=result, status_code=status_code)

@auth_bp.route("/me", methods=["GET"], strict_slashes=False)
@require_auth
def get_current_user():
    """
    Protected Endpoint: GET /api/v1/auth/me
    Requires valid JWT Bearer token.
    """
    user_context = {
        "id": request.user.id,
        "role": request.user.role,
        "institution_id": request.user.institution_id,
        "email": request.user.email
    }
    return success_response(data=user_context)
