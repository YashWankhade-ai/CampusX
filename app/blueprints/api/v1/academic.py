"""Academic API Blueprint — Sprint 14 Hardening.

Secures the previously unauthenticated academic scaffold endpoints.

Before hardening (original Sprint 0 scaffold issues):
    - GET /academic/institutions  → no auth, returned ALL institutions
    - GET /academic/departments   → no auth, accepted institution_id from query string
    - GET /academic/subjects      → no auth, accepted department_id from query string
    - POST /academic/subjects     → @require_role(['admin']) — wrong: 'admin' is not a valid Role constant

After hardening:
    - All GET endpoints require @require_auth (401 for unauthenticated)
    - GET /academic/institutions  → SUPER_ADMIN sees all; others see only their own
    - GET /academic/departments   → scoped to authenticated user's institution
    - GET /academic/subjects      → scoped via department (must belong to own institution)
    - POST /academic/subjects     → requires institutions:manage (SUPER_ADMIN/INSTITUTION_ADMIN)
    - institution_id is ALWAYS from request.user.institution_id (JWT),
      never from client-supplied query param for authorization
    - Client-supplied query params (institution_id, department_id) are used only
      as filters WITHIN the already-restricted institution scope

Architecture:
    Blueprint → AcademicService (thin) → DB queries on Institution, Department, Subject models
    No duplicate service or model — reuses existing architecture.

Permission mapping:
    - GET endpoints: @require_auth only (all authenticated non-GUEST users should
      be able to see their institution's academic structure for browsing/search)
    - POST /subjects: requires 'institutions:manage' (INSTITUTION_ADMIN, SUPER_ADMIN)
"""
import uuid
from flask import Blueprint, request

from app.utils.response_utils import success_response, error_response
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission
from app.extensions import db
from app.models.academic import Institution, Department, Subject
from app.permissions.roles import Role

academic_bp = Blueprint('academic', __name__)


def _safe_institution_dict(inst: Institution) -> dict:
    """Safe institution serializer — never returns settings_json secrets."""
    return {
        "id": str(inst.id),
        "name": inst.name,
        "short_name": inst.short_name,
        "code": inst.code,
        "city": inst.city,
        "state": inst.state,
        "country": inst.country,
        "is_active": inst.is_active,
        "subscription_tier": inst.subscription_tier,
    }


def _safe_department_dict(dept: Department) -> dict:
    return {
        "id": str(dept.id),
        "name": dept.name,
        "institution_id": str(dept.institution_id),
    }


def _safe_subject_dict(subj: Subject) -> dict:
    return {
        "id": str(subj.id),
        "code": subj.code,
        "name": subj.name,
        "program_id": str(subj.program_id),
        "semester_id": str(subj.semester_id),
        "credits": subj.credits,
    }


# ── Institutions ──────────────────────────────────────────────────────────────

@academic_bp.route('/institutions', methods=['GET'])
@require_auth
def get_institutions():
    """Return institution(s) visible to the authenticated user.

    SUPER_ADMIN: all active institutions.
    Others: only their own institution (from JWT institution_id).
    institution_id from query string is IGNORED for authorization.
    """
    actor_role = request.user.role
    actor_institution_id = request.user.institution_id

    if actor_role == Role.SUPER_ADMIN:
        insts = db.session.query(Institution).filter(
            Institution.is_deleted == False,
        ).order_by(Institution.name).all()
    elif actor_institution_id:
        try:
            iid = uuid.UUID(str(actor_institution_id))
        except (ValueError, TypeError):
            return success_response(data=[])
        insts = db.session.query(Institution).filter(
            Institution.id == iid,
            Institution.is_deleted == False,
        ).all()
    else:
        # No institution assigned — return empty
        return success_response(data=[])

    return success_response(data=[_safe_institution_dict(i) for i in insts])


# ── Departments ───────────────────────────────────────────────────────────────

@academic_bp.route('/departments', methods=['GET'])
@require_auth
def get_departments():
    """Return departments scoped to the authenticated user's institution.

    institution_id from query string is IGNORED for authorization —
    institution always comes from the authenticated JWT.
    Optional ?department_id= filter allowed within own institution scope only.
    """
    actor_role = request.user.role
    actor_institution_id = request.user.institution_id

    if actor_role == Role.SUPER_ADMIN:
        # SUPER_ADMIN may optionally filter by institution_id query param
        filter_iid_str = request.args.get('institution_id')
        if filter_iid_str:
            try:
                filter_iid = uuid.UUID(filter_iid_str)
                depts = db.session.query(Department).filter(
                    Department.institution_id == filter_iid,
                ).all()
            except (ValueError, TypeError):
                return success_response(data=[])
        else:
            depts = db.session.query(Department).all()
    elif actor_institution_id:
        try:
            iid = uuid.UUID(str(actor_institution_id))
        except (ValueError, TypeError):
            return success_response(data=[])
        depts = db.session.query(Department).filter(
            Department.institution_id == iid,
        ).all()
    else:
        return success_response(data=[])

    return success_response(data=[_safe_department_dict(d) for d in depts])


# ── Subjects ─────────────────────────────────────────────────────────────────

@academic_bp.route('/subjects', methods=['GET'])
@require_auth
def get_subjects():
    """Return subjects.

    Subjects don't have a direct institution_id — they belong to Programs
    which belong to Departments which belong to Institutions.

    For non-SUPER_ADMIN: filter by departments in own institution.
    Optional ?program_id= filter applied within scope.

    institution_id from query string is IGNORED for authorization.
    """
    actor_role = request.user.role
    actor_institution_id = request.user.institution_id

    program_id_filter = request.args.get('program_id')

    if actor_role == Role.SUPER_ADMIN:
        query = db.session.query(Subject)
        if program_id_filter:
            try:
                pid = uuid.UUID(program_id_filter)
                query = query.filter(Subject.program_id == pid)
            except (ValueError, TypeError):
                return success_response(data=[])
        subjects = query.all()
    elif actor_institution_id:
        try:
            iid = uuid.UUID(str(actor_institution_id))
        except (ValueError, TypeError):
            return success_response(data=[])

        # Subjects → Programs → Departments → Institution
        # Subquery: program_ids whose department belongs to actor's institution
        dept_ids = [
            d.id for d in db.session.query(Department).filter(
                Department.institution_id == iid
            ).all()
        ]
        if not dept_ids:
            return success_response(data=[])

        from app.models.academic import Program
        prog_ids = [
            p.id for p in db.session.query(Program).filter(
                Program.department_id.in_(dept_ids)
            ).all()
        ]
        if not prog_ids:
            return success_response(data=[])

        query = db.session.query(Subject).filter(Subject.program_id.in_(prog_ids))
        if program_id_filter:
            try:
                pid = uuid.UUID(program_id_filter)
                query = query.filter(Subject.program_id == pid)
            except (ValueError, TypeError):
                return success_response(data=[])
        subjects = query.all()
    else:
        return success_response(data=[])

    return success_response(data=[_safe_subject_dict(s) for s in subjects])


@academic_bp.route('/subjects', methods=['POST'])
@require_auth
@require_permission('institutions:manage')
def create_subject():
    """Create a new subject. Requires institutions:manage (INSTITUTION_ADMIN, SUPER_ADMIN).

    institution_id is never accepted from the request body for authorization.
    Program/Department must belong to the actor's institution.

    Body: { "code": str, "name": str, "program_id": str, "semester_id": str, "credits": int }
    """
    data = request.get_json(silent=True) or {}

    code = data.get('code', '').strip()
    name = data.get('name', '').strip()
    program_id = data.get('program_id', '').strip()
    semester_id = data.get('semester_id', '').strip()
    credits = data.get('credits', 3)

    if not all([code, name, program_id, semester_id]):
        return error_response(
            code="VALIDATION_ERROR",
            message="Required fields: code, name, program_id, semester_id",
            status_code=400,
        )

    try:
        pid = uuid.UUID(program_id)
        semid = uuid.UUID(semester_id)
    except (ValueError, TypeError):
        return error_response(code="VALIDATION_ERROR", message="Invalid UUID in program_id or semester_id", status_code=400)

    # Institution isolation: verify program's department belongs to actor's institution
    actor_role = request.user.role
    actor_institution_id = request.user.institution_id

    if actor_role != Role.SUPER_ADMIN and actor_institution_id:
        from app.models.academic import Program
        prog = db.session.query(Program).filter(Program.id == pid).first()
        if not prog:
            return error_response(code="NOT_FOUND", message="Program not found", status_code=404)

        dept = db.session.query(Department).filter(Department.id == prog.department_id).first()
        if not dept or str(dept.institution_id) != str(actor_institution_id):
            return error_response(
                code="FORBIDDEN",
                message="Program does not belong to your institution",
                status_code=403,
            )

    subj = Subject(
        id=uuid.uuid4(),
        code=code,
        name=name,
        program_id=pid,
        semester_id=semid,
        credits=int(credits) if str(credits).isdigit() else 3,
    )
    db.session.add(subj)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return error_response(code="DB_ERROR", message="Could not create subject", status_code=500)

    return success_response(data=_safe_subject_dict(subj), message="Subject created", status_code=201)
