from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.academic_service import AcademicService
from app.schemas.academic import SubjectSchema
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
