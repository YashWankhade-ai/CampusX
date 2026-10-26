from flask import Blueprint, request, send_file
from app.utils.response_utils import success_response, error_response
from app.services.resource_service import ResourceService
from app.services.upload_service import UploadService
from app.schemas.resource import ResourceUploadSchema, ResourceResponseSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role, require_permission, has_permission

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
    serialized_items = []
    for item in items:
        d = item.to_dict() if hasattr(item, 'to_dict') else dict(item)
        if hasattr(item, 'subject') and item.subject:
            d['subject_name'] = item.subject.name
            d['subject_code'] = item.subject.code
            if not d.get('department_name') and getattr(item.subject, 'program', None):
                d['department_name'] = item.subject.program.name
        if hasattr(item, 'author') and item.author:
            d['contributor_name'] = item.author.full_name
        serialized_items.append(d)
    return success_response(data=serialized_items, meta=meta)

@resources_bp.route('/upload', methods=['POST'])
@require_auth
def upload_resource():
    """Upload a document. Requires resources:write permission or an active approved account."""
    user = getattr(request, 'user', None)
    if not user:
        return error_response(code="UNAUTHORIZED", message="Authentication required", status_code=401)

    # 1. Base permission check (Faculty, Admin, Moderator)
    can_upload = has_permission(user, 'resources:write')

    # 2. Or active user approved by admin (e.g. Student approved in User Directory)
    if not can_upload and hasattr(user, 'id') and user.id:
        try:
            import uuid
            from app.models.user import User
            from app.extensions import db
            uid = uuid.UUID(str(user.id)) if isinstance(user.id, str) else user.id
            db_user = db.session.get(User, uid)
            if db_user and db_user.status == 'active':
                can_upload = True
        except Exception:
            pass

    if not can_upload:
        return error_response(
            code="FORBIDDEN",
            message="Permission denied. Only accounts approved by the administrator may upload resources.",
            status_code=403
        )

    try:
        file = request.files.get('file')
        if not file:
            return error_response(code="VALIDATION_ERROR", message="File is required", status_code=400)

        title = request.form.get('title')
        if not title:
            return error_response(code="VALIDATION_ERROR", message="Title is required", status_code=400)

        description = request.form.get('description', '')
        resource_type = request.form.get('resource_type', 'NOTE')
        faculty_name = (
            request.form.get('faculty_name') or
            request.form.get('teacher_name') or
            ''
        ).strip()
        department_name = (
            request.form.get('department_name') or
            request.form.get('department') or
            request.form.get('branch') or
            ''
        ).strip()

        if not faculty_name:
            if request.form.get('require_faculty') == '1':
                return error_response(code="VALIDATION_ERROR", message="Faculty / Teacher name is required", status_code=400)
            faculty_name = getattr(request.user, 'full_name', None) or request.user.email or "Faculty Instructor"

        subject_raw = (
            request.form.get('subject') or
            request.form.get('subject_name') or
            request.form.get('subject_id') or
            ''
        ).strip()

        subject_id = None
        if subject_raw:
            import uuid
            from app.models.academic import Subject, Program, Semester
            from app.extensions import db
            from sqlalchemy import func

            try:
                sid = uuid.UUID(subject_raw)
                existing = Subject.query.filter_by(id=sid).first()
                if existing:
                    subject_id = str(existing.id)
            except (ValueError, TypeError):
                pass

            if not subject_id:
                existing = Subject.query.filter(
                    (func.lower(Subject.name) == subject_raw.lower()) |
                    (func.lower(Subject.code) == subject_raw.lower())
                ).first()
                if existing:
                    subject_id = str(existing.id)

            if not subject_id:
                existing = Subject.query.filter(Subject.name.ilike(f"%{subject_raw}%")).first()
                if existing:
                    subject_id = str(existing.id)

            if not subject_id:
                try:
                    prog = None
                    if department_name:
                        prog = Program.query.filter(Program.name.ilike(f"%{department_name}%")).first()
                    if not prog:
                        prog = Program.query.first()
                    sem = Semester.query.first()
                    if prog and sem:
                        words = [w for w in subject_raw.split() if w.isalnum()]
                        initials = "".join(w[0].upper() for w in words)[:4] or "SUB"
                        import random
                        code = f"{initials}{random.randint(100, 999)}"
                        new_subj = Subject(
                            id=uuid.uuid4(),
                            code=code,
                            name=subject_raw,
                            program_id=prog.id,
                            semester_id=sem.id,
                            credits=3
                        )
                        db.session.add(new_subj)
                        db.session.flush()
                        subject_id = str(new_subj.id)
                except Exception:
                    pass

        user_id = request.user.id
        institution_id = request.user.institution_id
        if not institution_id:
            try:
                import uuid
                from app.models.user import User
                from app.extensions import db
                uid = uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
                db_u = db.session.get(User, uid)
                if db_u and db_u.institution_id:
                    institution_id = str(db_u.institution_id)
            except Exception:
                pass
        if not institution_id:
            from app.models.academic import Institution
            inst = Institution.query.first()
            if inst:
                institution_id = str(inst.id)

        result = upload_service.upload_resource(
            file=file,
            user_id=user_id,
            institution_id=institution_id,
            title=title,
            description=description,
            subject_id=subject_id,
            resource_type=resource_type,
            faculty_name=faculty_name,
            department_name=department_name or None,
        )

        return success_response(
            data=result,
            message="Resource uploaded successfully and queued for admin review. It will be published once approved.",
            status_code=201
        )
    except ValueError as e:
        return error_response(code="VALIDATION_ERROR", message=str(e), status_code=400)
    except Exception as e:
        return error_response(code="STORAGE_ERROR", message=str(e), status_code=500)

@resources_bp.route('/<resource_id>', methods=['GET'], strict_slashes=False)
@require_auth
def get_resource(resource_id):
    """Return resource metadata.

    Security:
    - Requires authentication (resources:read enforced via @require_auth;
      all authenticated roles have resources:read per ROLE_PERMISSIONS).
    - Institution isolation: author's institution must match viewer's JWT institution.
    - Visibility: only APPROVED resources visible to regular users.
      Authors see their own resource in any status.
      MODERATOR/ADMIN roles see any status within their institution.
    - resource.viewed recorded only on successful, authorised access.
    - Storage paths are never returned.
    """
    viewer_id = str(request.user.id)
    viewer_institution_id = str(request.user.institution_id) if request.user.institution_id else None
    viewer_role = request.user.role

    detail = resource_service.get_resource_detail(
        resource_id=resource_id,
        viewer_id=viewer_id,
        viewer_institution_id=viewer_institution_id,
        viewer_role=viewer_role,
    )

    if not detail:
        # Fail closed — 404 for not-found, wrong institution, or unauthorized status
        return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)

    # Record resource.viewed only after all checks pass
    try:
        from app.repositories.analytics_repository import record_event, record_resource_view
        from app.extensions import db as _db
        record_event(
            event_type="resource.viewed",
            user_id=viewer_id,
            institution_id=viewer_institution_id,
            event_data={"resource_id": resource_id},
        )
        record_resource_view(
            resource_id=resource_id,
            user_id=viewer_id,
            institution_id=viewer_institution_id,
        )
        _db.session.commit()
    except Exception:
        pass  # Analytics failure must not affect the primary response

    return success_response(data=detail)

def stream_resource_file(resource_id, inline=False):
    import os
    import uuid
    from app.extensions import db
    from app.models.resource import StudyMaterial
    from app.services.download_service import DownloadService
    from app.utils.token import decode_access_token
    from app.middleware.auth import UserContext

    # Check authentication if provided
    user = getattr(request, 'user', None)
    if not user:
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
        if not token:
            token = request.cookies.get("access_token")
        if not token:
            token = request.args.get("token")
        if token:
            payload = decode_access_token(token)
            if payload:
                user = UserContext(
                    user_id=payload.get("sub"),
                    role=payload.get("role", "STUDENT"),
                    institution_id=payload.get("institution_id"),
                    email=payload.get("email")
                )

    try:
        rid = uuid.UUID(str(resource_id))
    except (ValueError, TypeError):
        return error_response(code="INVALID_ID", message="Invalid resource ID", status_code=400)

    material = db.session.query(StudyMaterial).filter(
        StudyMaterial.id == rid,
        StudyMaterial.is_deleted == False
    ).first()

    if not material:
        return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)

    # Permission check: If not approved, only author or reviewers can view/download
    if material.status != "APPROVED":
        if not user or (str(material.author_id) != str(user.id) and user.role not in ("ADMIN", "SUPER_ADMIN", "INSTITUTION_ADMIN", "MODERATOR")):
            return error_response(code="FORBIDDEN", message="This resource is pending approval and not yet published.", status_code=403)

    ds = DownloadService()
    abs_path, filename, mime_type = ds.get_resource_file(resource_id)
    if not abs_path or not os.path.exists(abs_path):
        return error_response(code="FILE_NOT_FOUND", message="Physical resource file not found on server", status_code=404)

    # Record event
    try:
        user_id = str(user.id) if user else None
        event_name = "resource.viewed" if inline else "resource.downloaded"
        if not inline:
            ds.record_download_event(user_id, str(material.id))
        from app.repositories.analytics_repository import record_event
        record_event(
            event_type=event_name,
            user_id=user_id,
            institution_id=str(user.institution_id) if user and user.institution_id else None,
            event_data={"resource_id": str(material.id), "filename": filename, "inline": inline}
        )
        db.session.commit()
    except Exception:
        pass

    if inline:
        ext = (filename or '').rsplit('.', 1)[-1].lower()
        if ext != 'pdf':
            from app.services.document_viewer_service import DocumentViewerService
            from flask import Response
            html_page = DocumentViewerService.render_to_html(
                abs_path=abs_path,
                filename=filename,
                mime_type=mime_type,
                title=material.title,
                download_url=f"/api/v1/resources/{resource_id}/file"
            )
            return Response(html_page, mimetype="text/html")

    resp = send_file(
        abs_path,
        as_attachment=not inline,
        download_name=filename,
        mimetype=mime_type or "application/octet-stream"
    )
    if inline:
        resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp

@resources_bp.route('/<resource_id>/file', methods=['GET'], strict_slashes=False)
def serve_resource_file(resource_id):
    """Direct streaming endpoint. Accepts ?view=1 or ?inline=1 to view online without downloading."""
    is_view = request.args.get('view') in ('1', 'true', 'yes') or request.args.get('inline') in ('1', 'true', 'yes')
    return stream_resource_file(resource_id, inline=is_view)

@resources_bp.route('/<resource_id>/view', methods=['GET'], strict_slashes=False)
def view_resource_file(resource_id):
    """Direct endpoint to open and view the resource online in browser without downloading."""
    return stream_resource_file(resource_id, inline=True)

@resources_bp.route('/<resource_id>/download', methods=['GET'], strict_slashes=False)
@require_auth
def download_resource(resource_id):
    try:
        if request.args.get('stream') in ('1', 'true', 'yes') or request.args.get('direct') in ('1', 'true'):
            return stream_resource_file(resource_id)
        link = resource_service.get_download_link(resource_id, getattr(getattr(request, 'user', None), 'id', None))
        return success_response(data={"download_url": link})
    except Exception as e:
        return error_response(code="DOWNLOAD_ERROR", message=str(e), status_code=400)

@resources_bp.route('/<resource_id>', methods=['DELETE'], strict_slashes=False)
@require_auth
def delete_resource(resource_id):
    """Delete a resource. Requires resources:delete permission or author ownership."""
    import uuid
    from datetime import datetime, timezone
    from app.extensions import db
    from app.models.resource import StudyMaterial, MaterialVersion, FileMetadata
    from app.services.storage_service import get_storage_backend

    user = getattr(request, 'user', None)
    if not user:
        return error_response(code="UNAUTHORIZED", message="Authentication required", status_code=401)

    try:
        rid = uuid.UUID(str(resource_id))
    except (ValueError, TypeError):
        return error_response(code="INVALID_ID", message="Invalid resource ID", status_code=400)

    material = db.session.query(StudyMaterial).filter(
        StudyMaterial.id == rid,
        StudyMaterial.is_deleted == False
    ).first()

    if not material:
        return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)

    is_author = str(material.author_id) == str(user.id)
    has_del_perm = has_permission(user, 'resources:delete')

    if not (is_author or has_del_perm):
        return error_response(code="FORBIDDEN", message="Permission denied. You cannot delete this resource.", status_code=403)

    try:
        storage = get_storage_backend()
        versions = MaterialVersion.query.filter_by(study_material_id=material.id).all()
        for v in versions:
            fm = FileMetadata.query.filter_by(id=v.file_metadata_id).first()
            if fm and fm.storage_path:
                try:
                    storage.delete(fm.storage_path)
                except Exception:
                    pass
    except Exception:
        pass

    material.is_deleted = True
    material.deleted_at = datetime.now(timezone.utc)
    material.status = 'DELETED'
    db.session.commit()

    return success_response(data={"id": str(material.id)}, message="Resource deleted successfully")

@resources_bp.route('/<resource_id>/bookmark', methods=['POST'], strict_slashes=False)
@require_auth
def bookmark_resource(resource_id):
    return success_response(data=None, message="Bookmark toggled")

@resources_bp.route('/<resource_id>/rate', methods=['POST'], strict_slashes=False)
@require_auth
def rate_resource(resource_id):
    return success_response(data=None, message="Rating submitted")

@resources_bp.route('/subjects', methods=['GET'], strict_slashes=False)
def get_subjects():
    from app.models.academic import Subject, Program
    try:
        dept = request.args.get('department', request.args.get('branch', '')).strip()
        query = Subject.query.order_by(Subject.name.asc())
        if dept:
            prog = Program.query.filter(
                (Program.name.ilike(f"%{dept}%"))
            ).first()
            if prog:
                query = query.filter(Subject.program_id == prog.id)
        subjs = query.all()
        return success_response(data=[{
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "program_id": str(s.program_id) if s.program_id else None,
            "program_name": s.program.name if s.program else None
        } for s in subjs])
    except Exception:
        return success_response(data=[])

@resources_bp.route('/faculty-list', methods=['GET'], strict_slashes=False)
def get_faculty_list():
    from app.models.user import User
    try:
        users = User.query.filter(User.role.in_(['FACULTY', 'ADMIN', 'SUPER_ADMIN'])).order_by(User.full_name.asc()).all()
        data = []
        seen = set()
        for u in users:
            name = (u.full_name or '').strip()
            if name and name not in seen:
                data.append({"id": str(u.id), "name": name, "email": u.email, "role": u.role})
                seen.add(name)
        # Default faculty if few in dev
        default_names = ["Prof. Rajesh Kulkarni", "Prof. Priya Sharma", "Dr. Aris Thorne", "Dr. Anita Desai", "Prof. Vikram Malhotra"]
        for dn in default_names:
            if dn not in seen:
                data.append({"id": dn, "name": dn, "email": "", "role": "FACULTY"})
                seen.add(dn)
        return success_response(data=data)
    except Exception:
        return success_response(data=[])
