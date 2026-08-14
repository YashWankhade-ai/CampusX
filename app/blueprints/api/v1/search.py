import asyncio
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.ai.rag_service import RAGService

search_bp = Blueprint('search', __name__)
rag_service = RAGService()

@search_bp.route('', methods=['GET'], strict_slashes=False)
@search_bp.route('/', methods=['GET'], strict_slashes=False)
def hybrid_search():
    query = request.args.get('q', request.args.get('query', '')).strip()
    limit = request.args.get('limit', 10, type=int)
    institution_id = request.args.get('institution_id')
    department_id = request.args.get('department_id')
    semester_id = request.args.get('semester_id')
    subject_id = request.args.get('subject_id')

    user_role = getattr(getattr(request, 'user', None), 'role', 'GUEST')

    if not query:
        return success_response(data=[], meta={"query": "", "total": 0})

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            rag_service.hybrid_search(
                query=query,
                institution_id=institution_id,
                department_id=department_id,
                semester_id=semester_id,
                subject_id=subject_id,
                user_role=user_role,
                limit=limit
            )
        )
        meta = {
            "query": query,
            "total": len(results),
            "filters": {
                "institution_id": institution_id,
                "department_id": department_id,
                "semester_id": semester_id,
                "subject_id": subject_id,
                "user_role": user_role
            }
        }
        return success_response(data=results, meta=meta)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(code="SEARCH_ERROR", message=str(e), status_code=500)
    finally:
        loop.close()

@search_bp.route('/autocomplete', methods=['GET'], strict_slashes=False)
def autocomplete():
    query = request.args.get('query', '').strip()
    if not query:
        return success_response(data=[])
    suggestions = [
        f"{query} algorithms",
        f"{query} lecture notes",
        f"{query} previous year question papers",
        f"{query} assignment solutions"
    ]
    return success_response(data=suggestions)

@search_bp.route('/trending', methods=['GET'], strict_slashes=False)
def trending():
    trending_topics = [
        {"topic": "Data Structures & Algorithms", "searches": 1420},
        {"topic": "Artificial Intelligence & ML", "searches": 1180},
        {"topic": "Database Management Systems", "searches": 950},
        {"topic": "Operating Systems", "searches": 840}
    ]
    return success_response(data=trending_topics)
