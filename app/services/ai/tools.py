"""
Tool definitions and execution handlers for CampusX AI System
"""
from typing import Dict, Any, List
from app.extensions import db
from app.models.resource import StudyMaterial
from app.models.academic import Subject

# 1. Anthropic Tool Definitions
ANTHROPIC_TOOLS = [
    {
        "name": "search_study_materials",
        "description": "Search for study materials by title, subject, or query term.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term or keyword"},
                "limit": {"type": "integer", "description": "Number of results to return", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_subject_syllabus",
        "description": "Retrieve the course syllabus and unit outline for a subject code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Subject code e.g. CS301"}
            },
            "required": ["code"]
        }
    }
]

# 2. OpenAI Function Tool Definitions
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_study_materials",
            "description": "Search for study materials by title, subject, or query term.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term or keyword"},
                    "limit": {"type": "integer", "description": "Number of results to return", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_subject_syllabus",
            "description": "Retrieve the course syllabus and unit outline for a subject code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Subject code e.g. CS301"}
                },
                "required": ["code"]
            }
        }
    }
]

# 3. Tool Execution Handlers
def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tool calls and return JSON serializable dictionary results."""
    if tool_name == "search_study_materials":
        query = tool_args.get("query", "")
        limit = tool_args.get("limit", 5)
        materials = db.session.query(StudyMaterial).filter(
            StudyMaterial.title.ilike(f"%{query}%")
        ).limit(limit).all()

        results = [
            {
                "id": str(m.id),
                "title": m.title,
                "description": m.description,
                "material_type": m.material_type.value if hasattr(m.material_type, "value") else str(m.material_type),
                "status": m.status
            }
            for m in materials
        ]
        return {"results": results, "count": len(results)}

    elif tool_name == "get_subject_syllabus":
        code = tool_args.get("code", "").upper().strip()
        subject = db.session.query(Subject).filter_by(code=code).first()
        if not subject:
            return {"error": f"Subject with code '{code}' not found."}

        units_list = []
        for u in subject.units:
            topics = [{"id": str(t.id), "title": t.title, "description": t.description} for t in u.topics]
            units_list.append({
                "number": u.number,
                "title": u.title,
                "topics": topics
            })

        return {
            "code": subject.code,
            "name": subject.name,
            "credits": subject.credits,
            "units": units_list
        }

    return {"error": f"Unknown tool: {tool_name}"}
