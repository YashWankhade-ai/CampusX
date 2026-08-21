from flask import Blueprint, request, send_file
from app.utils.response_utils import success_response, error_response
from app.services.resource_service import ResourceService
from app.services.upload_service import UploadService
from app.schemas.resource import ResourceUploadSchema, ResourceResponseSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role, require_permission

resources_bp = Blueprint('resources', __name__, url_prefix='')
resource_service = ResourceService()
upload_service = UploadService()

@resources_bp.route('', methods=['GET'], strict_slashes=False)
@resources_bp.route('/', methods=['GET'], strict_slashes=False)
def list_resources():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    subject = request.args.get('subject')
    category = request.args.get('category')
    sort_by = request.args.get('sort_by', 'created_at')
    search = request.args.get('search')

    result = resource_service.list_resources(
        page=page, limit=limit, subject_id=subject, category_id=category, sort_by=sort_by, search=search
    )
    items = result.get('items', [])
    total = result.get('total', 0)
    meta = {"page": page, "limit": limit, "total": total}
    serialized_items = [item.to_dict() if hasattr(item, 'to_dict') else item for item in items]
    return success_response(data=serialized_items, meta=meta)

@resources_bp.route('/upload', methods=['POST'])
@require_auth
@require_permission('resources:write')
def upload_resource():
    """Upload a document. Requires resources:write permission."""
    try:
        file = request.files.get('file')
        if not file:
            return error_response(code="VALIDATION_ERROR", message="File is required", status_code=400)

        title = request.form.get('title')
        if not title:
            return error_response(code="VALIDATION_ERROR", message="Title is required", status_code=400)

        description = request.form.get('description', '')
        subject_id = request.form.get('subject_id')
        resource_type = request.form.get('resource_type', 'NOTE')

        user_id = request.user.id
        institution_id = request.user.institution_id

        result = upload_service.upload_resource(
            file=file,
            user_id=user_id,
            institution_id=institution_id,
            title=title,
            description=description,
            subject_id=subject_id,
            resource_type=resource_type
        )

        return success_response(data=result, message="Resource uploaded", status_code=201)
    except ValueError as e:
        return error_response(code="VALIDATION_ERROR", message=str(e), status_code=400)
    except Exception as e:
        return error_response(code="STORAGE_ERROR", message=str(e), status_code=500)

@resources_bp.route('/<resource_id>', methods=['GET'], strict_slashes=False)
def get_resource(resource_id):
    resource = resource_service.get_resource(resource_id)
    if not resource:
        return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)
    return success_response(data=resource)

@resources_bp.route('/<resource_id>/download', methods=['GET'], strict_slashes=False)
@require_auth
def download_resource(resource_id):
    try:
        link = resource_service.get_download_link(resource_id, getattr(getattr(request, 'user', None), 'id', None))
        return success_response(data={"download_url": link})
    except Exception as e:
        return error_response(code="DOWNLOAD_ERROR", message=str(e), status_code=400)

@resources_bp.route('/<resource_id>/bookmark', methods=['POST'], strict_slashes=False)
@require_auth
def bookmark_resource(resource_id):
    return success_response(data=None, message="Bookmark toggled")

@resources_bp.route('/<resource_id>/rate', methods=['POST'], strict_slashes=False)
@require_auth
def rate_resource(resource_id):
    return success_response(data=None, message="Rating submitted")
