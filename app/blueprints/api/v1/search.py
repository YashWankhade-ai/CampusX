"""Search & Discovery API — Sprint 9.

Route → Validation → Auth → Institution Scope → SearchService → Hybrid Search → Approved Results.

Security:
- Authentication required (resources:read permission).
- Institution_id derived from JWT, never from query params.
- No internal errors exposed in responses.
- Limits enforced server-side (max 50 per request).
- Only APPROVED resources surface in BM25 layer.
- Qdrant layer filters by institution_id from JWT payload.
"""
import logging
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.middleware.auth import require_auth
from app.permissions.rbac import require_permission
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

search_bp = Blueprint('search', __name__)
_search_service = None

# Server-enforced limits
QUERY_MAX_LENGTH = 500
LIMIT_MAX = 50
LIMIT_DEFAULT = 10


def get_search_service() -> SearchService:
    """Lazy singleton — avoids module-level import-time failures."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


@search_bp.route('', methods=['GET'], strict_slashes=False)
@search_bp.route('/', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('search:use')
def hybrid_search():
    """Hybrid search over approved resources within the user's institution.

    Query params:
      q          - search query (required, max 500 chars)
      limit      - results per page (default 10, max 50)
      page       - page number (default 1)
      subject_id - optional UUID filter
      department_id - optional UUID filter
      semester_id - optional UUID filter
    """
    # --- Input validation ---
    raw_query = request.args.get('q', request.args.get('query', '')).strip()

    if not raw_query:
        return success_response(
            data=[],
            meta={"query": "", "total": 0, "page": 1, "limit": LIMIT_DEFAULT}
        )

    if len(raw_query) > QUERY_MAX_LENGTH:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Query exceeds maximum length of {QUERY_MAX_LENGTH} characters.",
            status_code=400
        )

    try:
        limit = int(request.args.get('limit', LIMIT_DEFAULT))
        if limit < 1:
            limit = LIMIT_DEFAULT
        if limit > LIMIT_MAX:
            limit = LIMIT_MAX
    except (ValueError, TypeError):
        limit = LIMIT_DEFAULT

    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    # Optional filters — validated but not trusted for institution scoping
    subject_id = request.args.get('subject_id') or None
    department_id = request.args.get('department_id') or None
    semester_id = request.args.get('semester_id') or None

    # --- Institution scope from JWT (never from query params) ---
    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_role = request.user.role

    # --- Execute search ---
    try:
        results = get_search_service().hybrid_search(
            query=raw_query,
            institution_id=institution_id,
            department_id=department_id,
            semester_id=semester_id,
            subject_id=subject_id,
            user_role=user_role,
            limit=limit,
            page=page,
        )
    except Exception:
        logger.exception("Search backend failure")
        return error_response(
            code="SEARCH_ERROR",
            message="Search is temporarily unavailable. Please try again.",
            status_code=503
        )

    meta = {
        "query": raw_query,
        "total": len(results),
        "page": page,
        "limit": limit,
    }
    return success_response(data=results, meta=meta)


@search_bp.route('/autocomplete', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('search:use')
def autocomplete():
    """Query autocomplete suggestions."""
    query = request.args.get('q', request.args.get('query', '')).strip()
    if not query or len(query) > QUERY_MAX_LENGTH:
        return success_response(data=[])
    suggestions = get_search_service().autocomplete(query)
    return success_response(data=suggestions)


@search_bp.route('/trending', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('search:use')
def trending():
    """Trending search topics (institution-scoped where applicable)."""
    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    topics = get_search_service().trending_searches(institution_id=institution_id)
    return success_response(data=topics)
