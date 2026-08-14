from flask import Blueprint, request
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
