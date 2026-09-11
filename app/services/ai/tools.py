"""Tool definitions and execution handlers for CampusX AI System.

Security contract:
    - execute_tool() MUST receive institution_id from the JWT-authenticated context.
    - search_study_materials filters by institution via User.institution_id join.
    - If no institution_id is provided, search returns empty results (fail closed).
    - Only APPROVED, non-deleted materials are ever returned.
    - Raw exception messages are NEVER propagated to callers.
"""
import uuid
import logging
from typing import Dict, Any, List, Optional

from app.extensions import db
from app.models.resource import StudyMaterial
from app.models.academic import Subject

logger = logging.getLogger(__name__)

# ── Anthropic tool definitions ─────────────────────────────────────────────────

ANTHROPIC_TOOLS = [
    {
        "name": "search_study_materials",
        "description": (
            "Search for approved study materials within the user's institution "
            "by title, subject, or keyword. Returns only approved, non-deleted materials."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term or keyword"},
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_subject_syllabus",
        "description": "Retrieve the course syllabus and unit outline for a subject code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Subject code e.g. CS301"},
            },
            "required": ["code"],
        },
    },
]

# ── OpenAI function tool definitions ──────────────────────────────────────────

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_study_materials",
            "description": (
                "Search for approved study materials within the user's institution "
                "by title, subject, or keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term or keyword"},
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (max 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subject_syllabus",
            "description": "Retrieve the course syllabus and unit outline for a subject code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Subject code e.g. CS301"},
                },
                "required": ["code"],
            },
        },
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    institution_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a named tool and return a JSON-serialisable dict.

    Args:
        tool_name:      Name of the tool to execute.
        tool_args:      Arguments provided by the LLM for the tool call.
        institution_id: From the JWT-authenticated user. NEVER from client input.
                        Required for search_study_materials — returns empty results
                        if not provided (fail closed, not error).

    Returns:
        Tool result dict. Never raises — errors are returned as {"error": ...}.
    """
    if tool_name == "search_study_materials":
        return _search_study_materials(tool_args, institution_id)

    if tool_name == "get_subject_syllabus":
        return _get_subject_syllabus(tool_args)

    return {"error": f"Unknown tool: {tool_name}"}


def _search_study_materials(
    tool_args: Dict[str, Any],
    institution_id: Optional[str],
) -> Dict[str, Any]:
    """Search APPROVED study materials scoped to the authenticated user's institution.

    Security:
        - institution_id MUST come from the JWT. Never trust tool_args for this.
        - If institution_id is absent or invalid, return empty results (fail closed).
        - Only APPROVED, is_deleted=False materials are returned.
    """
    query = tool_args.get("query", "")
    limit = min(int(tool_args.get("limit", 5)), 10)  # cap at 10

    # Fail closed: without institution_id we cannot scope results safely.
    if not institution_id:
        logger.warning("[Tool] search_study_materials called without institution_id — returning empty")
        return {"results": [], "count": 0}

    try:
        inst_uuid = uuid.UUID(str(institution_id))
    except (ValueError, TypeError):
        logger.warning("[Tool] search_study_materials: invalid institution_id format — returning empty")
        return {"results": [], "count": 0}

    try:
        from app.models.user import User  # deferred to avoid circular import

        materials = (
            db.session.query(StudyMaterial)
            .join(User, StudyMaterial.author_id == User.id)
            .filter(
                StudyMaterial.title.ilike(f"%{query}%"),
                StudyMaterial.status == "APPROVED",
                StudyMaterial.is_deleted == False,  # noqa: E712
                User.institution_id == inst_uuid,
            )
            .limit(limit)
            .all()
        )

        results = [
            {
                "id": str(m.id),
                "title": m.title,
                "description": m.description,
                "material_type": (
                    m.material_type.value
                    if hasattr(m.material_type, "value")
                    else str(m.material_type)
                ),
            }
            for m in materials
        ]
        return {"results": results, "count": len(results)}

    except Exception as exc:
        logger.error("[Tool] search_study_materials DB error: %s", type(exc).__name__)
        return {"results": [], "count": 0, "error": "Search unavailable"}


def _get_subject_syllabus(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve syllabus for a subject by code. Not institution-scoped (codes are global)."""
    code = tool_args.get("code", "").upper().strip()
    if not code:
        return {"error": "Subject code is required."}

    try:
        subject = db.session.query(Subject).filter_by(code=code).first()
        if not subject:
            return {"error": f"Subject with code '{code}' not found."}

        units_list = []
        for u in subject.units:
            topics = [
                {"id": str(t.id), "title": t.title, "description": t.description}
                for t in u.topics
            ]
            units_list.append({
                "number": u.number,
                "title": u.title,
                "topics": topics,
            })

        return {
            "code": subject.code,
            "name": subject.name,
            "credits": subject.credits,
            "units": units_list,
        }

    except Exception as exc:
        logger.error("[Tool] get_subject_syllabus DB error: %s", type(exc).__name__)
        return {"error": "Syllabus lookup unavailable"}
