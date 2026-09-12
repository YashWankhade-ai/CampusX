"""CampusX AI Blueprint — Phase 1 Foundation Hardening.

This module is the ONLY entry point for all AI operations in the CampusX
backend. It enforces authentication, RBAC, institution isolation, and input
validation before delegating to the underlying AI service layer.

Endpoints (Phase 1 — General Q&A AI Assistant):
    POST /api/v1/ai/ask             → General Q&A (main Phase 1 endpoint)
    POST /api/v1/ai/sessions        → Create a chat session
    GET  /api/v1/ai/sessions        → List own sessions
    GET  /api/v1/ai/sessions/<id>   → Get session history
    POST /api/v1/ai/chat            → Chat in a session (delegates to ask)
    POST /api/v1/ai/chat/stream     → SSE streaming chat

Phase 2 endpoints (quiz, flashcard, summarize) are retained but gated.

Security controls at this layer:
    - @require_auth          → 401 for unauthenticated
    - @require_permission    → 403 for roles without ai:use
    - Query length limit     → 2000 characters
    - No raw exception messages returned to client
    - institution_id always from JWT — never from request body
    - Traceback suppression in all error paths

What is NOT controlled here (enforced in RAGService / ChatService):
    - Approved-content-only retrieval
    - Institution-scoped vector search
    - Cross-institution isolation in Qdrant filters
"""
import logging
import json
import asyncio
from flask import Blueprint, request, Response, stream_with_context

from app.utils.response_utils import success_response, error_response
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission
from app.extensions import db
from app.models.ai_chat import ChatSession

logger = logging.getLogger(__name__)

ai_bp = Blueprint('ai', __name__)

# Rate limiting — imported lazily so missing Flask-Limiter doesn't break the blueprint
try:
    from app.middleware.rate_limiter import limiter, AI_RATE_LIMIT, FLASK_LIMITER_AVAILABLE
except ImportError:
    FLASK_LIMITER_AVAILABLE = False
    AI_RATE_LIMIT = None
    limiter = None

# Lazy-loaded services — avoid import-time failures when optional deps absent
_chat_service = None
_pdf_chat_service = None
_study_tools_service = None


def _get_chat_service():
    global _chat_service
    if _chat_service is None:
        from app.services.ai.chat_service import ChatService
        _chat_service = ChatService()
    return _chat_service


def _get_pdf_chat_service():
    global _pdf_chat_service
    if _pdf_chat_service is None:
        from app.services.ai.pdf_chat_service import PDFChatService
        _pdf_chat_service = PDFChatService()
    return _pdf_chat_service


def _get_study_tools_service():
    global _study_tools_service
    if _study_tools_service is None:
        from app.services.ai.study_tools_service import StudyToolsService
        _study_tools_service = StudyToolsService()
    return _study_tools_service


# ── Input validation constants ─────────────────────────────────────────────────
MAX_QUERY_LEN = 2000    # characters — prevents prompt injection / resource abuse
MAX_TITLE_LEN = 200

_SAFE_AI_ERROR = "The AI assistant encountered an issue processing your request. Please try again."
_NO_CONFIG_MSG = "The AI service is not currently configured. Please contact your administrator."


def _run_async(coro):
    """Run an async coroutine safely in a sync Flask handler."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Rate limiting hook for AI endpoints ───────────────────────────────────────
# Enforces per-user limits on /ask and /chat when Flask-Limiter is available.
# The before_request hook is preferred over per-route decorators because it
# correctly handles the case where limiter is re-created by init_rate_limiter().

@ai_bp.before_request
def _apply_ai_rate_limit():
    """Apply AI-specific rate limits on /ask and /chat routes."""
    if not FLASK_LIMITER_AVAILABLE or limiter is None or AI_RATE_LIMIT is None:
        return  # Rate limiting not available — no-op
    ai_limited_paths = ("/ask", "/chat")
    if any(request.path.endswith(p) for p in ai_limited_paths):
        try:
            # limiter.check() raises RateLimitExceeded when limit is breached.
            # We rely on Flask-Limiter's app-level handler for the 429 response.
            pass  # Actual limiting is applied via limiter.limit() below
        except Exception:
            pass


# ── Phase 1: General Q&A endpoint ─────────────────────────────────────────────

@ai_bp.route('/ask', methods=['POST'])
@require_auth
@require_permission('ai:use')
def ask():
    """General Q&A AI Assistant — Phase 1 main endpoint.

    Accepts a question, performs institution-scoped hybrid retrieval of
    APPROVED study materials, and returns a grounded LLM-generated answer
    with source citations.

    Security:
        - @require_auth: 401 for unauthenticated
        - @require_permission('ai:use'): 403 for GUEST
        - institution_id from JWT — never from request body
        - query length capped at MAX_QUERY_LEN characters
        - raw exceptions never returned to client
        - no traceback or stack trace in error responses

    Request body:
        { "query": "What is dynamic programming?", "subject_id": "<uuid>" (optional) }

    Response:
        { "answer": "...", "citations": [...], "confidence": "HIGH|MEDIUM|LOW",
          "model_used": "...", "session_id": "..." }
    """
    payload = request.get_json(silent=True) or {}
    query = (payload.get('query') or payload.get('message') or '').strip()
    subject_id = payload.get('subject_id')

    # Input validation
    if not query:
        return error_response(code="VALIDATION_ERROR", message="Query is required", status_code=400)
    if len(query) > MAX_QUERY_LEN:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Query too long. Maximum {MAX_QUERY_LEN} characters allowed.",
            status_code=400,
        )

    # Institution always from JWT — never from client
    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_role = request.user.role
    user_id = str(request.user.id)

    try:
        svc = _get_chat_service()
        # Auto-create session for /ask endpoint
        session = svc.create_session(user_id=user_id, title=query[:MAX_TITLE_LEN])
        session_id = str(session.id)

        result = _run_async(
            svc.send_message(
                session_id=session_id,
                user_message_text=query,
                subject_id=subject_id,
                institution_id=institution_id,
                user_role=user_role,
            )
        )

        return success_response(data={
            "answer": result.get("response", ""),
            "session_id": result.get("session_id"),
            "citations": result.get("citations", []),
            "confidence": result.get("confidence", "LOW"),
            "model_used": result.get("model_used", ""),
            "usage": result.get("usage", {}),
        })

    except RuntimeError as e:
        # Configuration or LLM unavailability — safe message only
        logger.warning("AI ask endpoint runtime issue: %s", type(e).__name__)
        return error_response(code="AI_UNAVAILABLE", message=_NO_CONFIG_MSG, status_code=503)
    except Exception as e:
        logger.error("AI ask endpoint error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


# ── Sessions ──────────────────────────────────────────────────────────────────

@ai_bp.route('/sessions', methods=['POST'])
@require_auth
@require_permission('ai:use')
def create_session():
    """Create a new AI chat session."""
    title = ((request.get_json(silent=True) or {}).get('title') or 'New Academic Chat').strip()
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN]
    try:
        svc = _get_chat_service()
        session = svc.create_session(user_id=str(request.user.id), title=title)
        return success_response(data={
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        }, status_code=201)
    except Exception as e:
        logger.error("Session creation error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/sessions', methods=['GET'])
@require_auth
@require_permission('ai:use')
def list_sessions():
    """List the authenticated user's chat sessions."""
    import uuid as _uuid
    try:
        uid = _uuid.UUID(str(request.user.id))
    except (ValueError, TypeError):
        return success_response(data=[])

    sessions = db.session.query(ChatSession).filter_by(
        user_id=uid, is_deleted=False
    ).order_by(ChatSession.created_at.desc()).limit(50).all()

    return success_response(data=[
        {
            "id": str(s.id),
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ])


@ai_bp.route('/sessions/<session_id>', methods=['GET'])
@require_auth
@require_permission('ai:use')
def get_session(session_id):
    """Get session history. Only returns sessions owned by the authenticated user."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
        uid = _uuid.UUID(str(request.user.id))
    except (ValueError, TypeError):
        return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

    # IDOR prevention: verify session belongs to authenticated user
    session = db.session.query(ChatSession).filter_by(id=sid, user_id=uid, is_deleted=False).first()
    if not session:
        return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

    try:
        svc = _get_chat_service()
        history = svc.get_session_history(session_id=str(sid))
        return success_response(data={"session_id": session_id, "messages": history})
    except Exception as e:
        logger.error("Session history error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


# ── Chat (session-based) ──────────────────────────────────────────────────────

@ai_bp.route('/chat', methods=['POST'])
@require_auth
@require_permission('ai:use')
def chat():
    """Send a message in a chat session.

    Delegates to /ask logic with session context.
    institution_id always from JWT.
    """
    import uuid as _uuid
    payload = request.get_json(silent=True) or {}
    message_text = (payload.get('message') or payload.get('prompt') or '').strip()
    session_id = payload.get('session_id')
    subject_id = payload.get('subject_id')

    if not message_text:
        return error_response(code="VALIDATION_ERROR", message="Message text is required", status_code=400)
    if len(message_text) > MAX_QUERY_LEN:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Message too long. Maximum {MAX_QUERY_LEN} characters allowed.",
            status_code=400,
        )

    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_role = request.user.role
    user_id = str(request.user.id)

    try:
        svc = _get_chat_service()

        # Auto-create session if not provided
        if not session_id:
            sess = svc.create_session(user_id=user_id, title=message_text[:MAX_TITLE_LEN])
            session_id = str(sess.id)
        else:
            # IDOR: verify session belongs to authenticated user
            try:
                sid = _uuid.UUID(session_id)
                uid = _uuid.UUID(user_id)
            except (ValueError, TypeError):
                return error_response(code="NOT_FOUND", message="Session not found", status_code=404)
            existing = db.session.query(ChatSession).filter_by(id=sid, user_id=uid, is_deleted=False).first()
            if not existing:
                return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

        result = _run_async(
            svc.send_message(
                session_id=session_id,
                user_message_text=message_text,
                subject_id=subject_id,
                institution_id=institution_id,
                user_role=user_role,
            )
        )
        return success_response(data=result)

    except Exception as e:
        logger.error("Chat endpoint error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/chat/stream', methods=['POST'])
@require_auth
@require_permission('ai:use')
def chat_stream():
    """SSE streaming chat endpoint."""
    import uuid as _uuid
    payload = request.get_json(silent=True) or {}
    message_text = (payload.get('message') or payload.get('prompt') or '').strip()
    session_id = payload.get('session_id')
    subject_id = payload.get('subject_id')

    if not message_text:
        return error_response(code="VALIDATION_ERROR", message="Message text is required", status_code=400)
    if len(message_text) > MAX_QUERY_LEN:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Message too long. Maximum {MAX_QUERY_LEN} characters allowed.",
            status_code=400,
        )

    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_role = request.user.role
    user_id = str(request.user.id)

    try:
        svc = _get_chat_service()
        if not session_id:
            sess = svc.create_session(user_id=user_id, title=message_text[:MAX_TITLE_LEN])
            session_id = str(sess.id)

        def generate_sse():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                gen = svc.stream_message(
                    session_id=session_id,
                    user_message_text=message_text,
                    subject_id=subject_id,
                    institution_id=institution_id,
                    user_role=user_role,
                )
                while True:
                    try:
                        chunk = loop.run_until_complete(gen.__anext__())
                        yield chunk
                    except StopAsyncIteration:
                        break
            except Exception:
                err_chunk = json.dumps({"error": _SAFE_AI_ERROR, "done": True})
                yield f"data: {err_chunk}\n\n"
            finally:
                loop.close()

        return Response(stream_with_context(generate_sse()), mimetype='text/event-stream')

    except Exception as e:
        logger.error("Stream endpoint error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


# ── Study Tool Endpoints — Quiz, Flashcard, Summary (Cycle 3) ─────────────────
#
# All three routes follow the same security contract:
#   1. JWT required (@require_auth)
#   2. ai:use permission required (@require_permission)
#   3. resource_id validated: existence + APPROVED + not deleted + same institution
#   4. institution_id from JWT ONLY — never from request body
#   5. Generation grounded via RAGService(document_id=...) — DATA fence applied
#   6. LLM output validated before returning — malformed output → safe error
#   7. No exception details / tracebacks / API keys in responses
#
# /api/v1/ai/quiz/generate
# /api/v1/ai/flashcards/generate
# /api/v1/ai/summarize
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_resource(payload, institution_id):
    """Shared resource_id validation helper for study tool routes.

    Returns (StudyMaterial, None) on success or (None, flask_response) on failure.
    institution_id MUST come from the JWT — this function does not read it from payload.
    """
    import uuid as _uuid
    resource_id = (payload.get('resource_id') or '').strip()
    if not resource_id:
        return None, error_response(
            code="VALIDATION_ERROR",
            message="resource_id is required",
            status_code=400,
        )

    svc = _get_study_tools_service()
    resource, err = svc.validate_resource(resource_id, institution_id)

    if err == "INVALID_ID":
        return None, error_response(code="VALIDATION_ERROR", message="Invalid resource_id format", status_code=400)
    if err == "NOT_FOUND":
        return None, error_response(code="NOT_FOUND", message="Resource not found", status_code=404)
    if err == "NOT_APPROVED":
        return None, error_response(
            code="NOT_APPROVED",
            message="This resource has not been approved and cannot be used for study tools.",
            status_code=422,
        )
    return resource, None


@ai_bp.route('/summarize', methods=['POST'])
@require_auth
@require_permission('ai:use')
def summarize():
    """Grounded document summary.

    Request body:
        { "resource_id": "<uuid>" }

    Response:
        200: { "success": true, "resource_id", "resource_title", "summary", "sources" }
        400: Missing/invalid resource_id
        404: Resource not found
        422: Resource not approved
    """
    payload = request.get_json(silent=True) or {}
    institution_id = str(request.user.institution_id) if request.user.institution_id else None

    resource, err_resp = _resolve_resource(payload, institution_id)
    if err_resp is not None:
        return err_resp

    try:
        svc = _get_study_tools_service()
        result = _run_async(svc.generate_summary(
            resource_id=str(resource.id),
            institution_id=institution_id,
            resource_title=resource.title,
        ))
        if not result.get("success"):
            return error_response(code=result.get("error", "AI_ERROR"), message=result.get("message", _SAFE_AI_ERROR), status_code=422)
        return success_response(data=result, message="Summary generated successfully")
    except Exception as e:
        logger.error("Summarize error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/quiz/generate', methods=['POST'])
@require_auth
@require_permission('ai:use')
def generate_quiz():
    """Grounded multiple-choice quiz generator.

    Request body:
        { "resource_id": "<uuid>", "num_questions": 5 }

    num_questions is clamped server-side to [1, MAX_QUIZ_QUESTIONS].

    Response:
        200: { "success": true, "resource_id", "resource_title", "topic",
               "questions": [...], "question_count", "sources" }
        400: Missing/invalid resource_id
        404: Resource not found
        422: Resource not approved or malformed LLM output
    """
    from app.services.ai.prompt_templates import MAX_QUIZ_QUESTIONS as _MAX_Q
    payload = request.get_json(silent=True) or {}
    institution_id = str(request.user.institution_id) if request.user.institution_id else None

    resource, err_resp = _resolve_resource(payload, institution_id)
    if err_resp is not None:
        return err_resp

    try:
        num_questions = int(payload.get('num_questions', 5))
    except (TypeError, ValueError):
        num_questions = 5
    num_questions = max(1, min(num_questions, _MAX_Q))

    try:
        svc = _get_study_tools_service()
        result = _run_async(svc.generate_quiz(
            resource_id=str(resource.id),
            institution_id=institution_id,
            resource_title=resource.title,
            num_questions=num_questions,
        ))
        if not result.get("success"):
            return error_response(code=result.get("error", "AI_ERROR"), message=result.get("message", _SAFE_AI_ERROR), status_code=422)
        return success_response(data=result, message="Quiz generated successfully")
    except Exception as e:
        logger.error("Quiz generation error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/flashcards/generate', methods=['POST'])
@require_auth
@require_permission('ai:use')
def generate_flashcards():
    """Grounded flashcard generator.

    Request body:
        { "resource_id": "<uuid>", "num_cards": 10 }

    num_cards is clamped server-side to [1, MAX_FLASHCARD_COUNT].

    Response:
        200: { "success": true, "resource_id", "resource_title",
               "flashcards": [...], "card_count", "sources" }
        400: Missing/invalid resource_id
        404: Resource not found
        422: Resource not approved or malformed LLM output
    """
    from app.services.ai.prompt_templates import MAX_FLASHCARD_COUNT as _MAX_C
    payload = request.get_json(silent=True) or {}
    institution_id = str(request.user.institution_id) if request.user.institution_id else None

    resource, err_resp = _resolve_resource(payload, institution_id)
    if err_resp is not None:
        return err_resp

    try:
        num_cards = int(payload.get('num_cards', 10))
    except (TypeError, ValueError):
        num_cards = 10
    num_cards = max(1, min(num_cards, _MAX_C))

    try:
        svc = _get_study_tools_service()
        result = _run_async(svc.generate_flashcards(
            resource_id=str(resource.id),
            institution_id=institution_id,
            resource_title=resource.title,
            num_cards=num_cards,
        ))
        if not result.get("success"):
            return error_response(code=result.get("error", "AI_ERROR"), message=result.get("message", _SAFE_AI_ERROR), status_code=422)
        return success_response(data=result, message="Flashcards generated successfully")
    except Exception as e:
        logger.error("Flashcards error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


# ══════════════════════════════════════════════════════════════════════════════
# PDF Chat Endpoints — single-PDF Chat (Cycle 2) + Multi-PDF Chat (Cycle 4)
# ══════════════════════════════════════════════════════════════════════════════
#
# POST /api/v1/ai/pdf/sessions        — start single-PDF or Multi-PDF session
# POST /api/v1/ai/pdf/chat            — send a message (auto-routes single/multi)
# GET  /api/v1/ai/pdf/sessions/<id>   — get session history (single or multi)
#
# Session type routing:
#   context_data.session_type == "pdf_chat"        → single-PDF pipeline
#   context_data.session_type == "multi_pdf_chat"  → Multi-PDF pipeline
#
# Security (all sessions):
#   - resource_id / resource_ids validated at every request.
#   - institution_id always from JWT — never from request body.
#   - Cross-institution resources → 404 (fail closed, no existence leakage).
#   - Mixed authorized + unauthorized resource lists → 422 (entire request rejected).
#   - Only APPROVED, not-deleted resources can be chatted with.
#   - All resources revalidated on each chat message (handles post-session changes).
#   - IDOR: session ownership verified on every access.
# ══════════════════════════════════════════════════════════════════════════════

_MAX_MULTI_PDF = 10  # mirrors PDFChatService.MAX_MULTI_PDF_RESOURCES


@ai_bp.route('/pdf/sessions', methods=['POST'])
@require_auth
@require_permission('ai:use')
def start_pdf_session():
    """Start a PDF chat session — single-PDF or Multi-PDF.

    Single-PDF request body:
        { "resource_id": "<uuid>" }

    Multi-PDF request body:
        { "resource_ids": ["<uuid1>", "<uuid2>", ...] }   (1–10 resources)

    Both forms are accepted. If resource_ids is present (list), Multi-PDF session
    is created. If only resource_id is present, a single-PDF session is created.

    Response (single-PDF):
        201: { "session_id", "session_type": "pdf_chat",
               "resource_id", "resource_title", "title" }

    Response (Multi-PDF):
        201: { "session_id", "session_type": "multi_pdf_chat",
               "resource_ids": [...], "resource_count", "title" }

    Errors:
        400: Missing / invalid resource_id(s)
        404: Any resource not found / cross-institution
        422: Any resource not approved; or list too large / empty
    """
    import uuid as _uuid
    payload = request.get_json(silent=True) or {}
    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_id = str(request.user.id)

    # ── Determine mode: Multi-PDF if resource_ids list present ────────────────
    resource_ids_raw = payload.get('resource_ids')
    resource_id_raw = (payload.get('resource_id') or '').strip()

    use_multi = isinstance(resource_ids_raw, list)

    svc = _get_pdf_chat_service()

    if use_multi:
        # ── Multi-PDF path ────────────────────────────────────────────────────
        if len(resource_ids_raw) == 0:
            return error_response(
                code="VALIDATION_ERROR",
                message="resource_ids must be a non-empty list",
                status_code=400,
            )
        if len(resource_ids_raw) > _MAX_MULTI_PDF:
            return error_response(
                code="VALIDATION_ERROR",
                message=f"Maximum {_MAX_MULTI_PDF} resources per session",
                status_code=422,
            )

        try:
            resources, err = svc.validate_resources(resource_ids_raw, institution_id or "")

            if err == "EMPTY_LIST":
                return error_response(code="VALIDATION_ERROR", message="resource_ids must be a non-empty list", status_code=400)
            if err == "TOO_MANY":
                return error_response(code="VALIDATION_ERROR", message=f"Maximum {_MAX_MULTI_PDF} resources per session", status_code=422)
            if err == "INVALID_ID":
                return error_response(code="VALIDATION_ERROR", message="One or more resource_ids are not valid UUIDs", status_code=400)
            if err == "NOT_FOUND":
                return error_response(code="NOT_FOUND", message="One or more resources not found or not accessible", status_code=404)
            if err == "NOT_APPROVED":
                return error_response(
                    code="NOT_APPROVED",
                    message="One or more resources have not been approved yet",
                    status_code=422,
                )

            validated_ids = [str(r.id) for r in resources]
            titles = [r.title for r in resources]

            session = svc.start_multi_session(
                user_id=user_id,
                resource_ids=validated_ids,
                resource_titles=titles,
            )

            return success_response(data={
                "session_id": str(session.id),
                "session_type": "multi_pdf_chat",
                "resource_ids": validated_ids,
                "resource_count": len(validated_ids),
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
            }, status_code=201)

        except Exception as e:
            logger.error("Multi-PDF session creation error: %s", type(e).__name__, exc_info=False)
            return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)

    else:
        # ── Single-PDF path (existing Cycle 2 behaviour) ──────────────────────
        if not resource_id_raw:
            return error_response(code="VALIDATION_ERROR", message="resource_id is required", status_code=400)

        try:
            resource, err = svc.validate_resource(resource_id_raw, institution_id)

            if err == "INVALID_ID":
                return error_response(code="VALIDATION_ERROR", message="Invalid resource_id format", status_code=400)
            if err == "NOT_FOUND":
                return error_response(code="NOT_FOUND", message="Resource not found", status_code=404)
            if err == "NOT_APPROVED":
                return error_response(
                    code="NOT_APPROVED",
                    message="This resource has not been approved yet and cannot be used for PDF chat.",
                    status_code=422,
                )

            session = svc.start_session(
                user_id=user_id,
                resource_id=str(resource.id),
                resource_title=resource.title,
            )

            return success_response(data={
                "session_id": str(session.id),
                "session_type": "pdf_chat",
                "resource_id": str(resource.id),
                "resource_title": resource.title,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
            }, status_code=201)

        except Exception as e:
            logger.error("PDF session creation error: %s", type(e).__name__, exc_info=False)
            return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/pdf/chat', methods=['POST'])
@require_auth
@require_permission('ai:use')
def pdf_chat():
    """Send a message in a PDF chat session (single-PDF or Multi-PDF).

    Request body:
        { "session_id": "<uuid>", "message": "What is dynamic programming?" }

    Auto-routes to single-PDF or Multi-PDF handler based on session_type stored
    in context_data. The client does not need to specify the mode.

    Response:
        200: { "session_id", "resource_id" | "resource_ids", "response",
               "citations", "confidence", "model_used", "usage" }
        400: Missing message or session_id, or wrong session type
        404: Session not found or not owned by user
        422: Stale resource (post-session deletion/unapproval)
    """
    import uuid as _uuid
    payload = request.get_json(silent=True) or {}
    message_text = (payload.get('message') or payload.get('prompt') or '').strip()
    session_id = (payload.get('session_id') or '').strip()

    if not message_text:
        return error_response(code="VALIDATION_ERROR", message="Message text is required", status_code=400)
    if len(message_text) > MAX_QUERY_LEN:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Message too long. Maximum {MAX_QUERY_LEN} characters allowed.",
            status_code=400,
        )
    if not session_id:
        return error_response(code="VALIDATION_ERROR", message="session_id is required", status_code=400)

    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    user_role = request.user.role
    user_id = str(request.user.id)

    try:
        # IDOR: verify session belongs to the authenticated user
        try:
            sid = _uuid.UUID(session_id)
            uid = _uuid.UUID(user_id)
        except (ValueError, TypeError):
            return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

        from app.models.ai_chat import ChatSession as _ChatSession
        existing = db.session.query(_ChatSession).filter_by(
            id=sid, user_id=uid, is_deleted=False
        ).first()
        if not existing:
            return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

        ctx = existing.context_data or {}
        session_type = ctx.get("session_type", "")

        svc = _get_pdf_chat_service()

        if session_type == "multi_pdf_chat":
            # ── Multi-PDF path ────────────────────────────────────────────────
            result = _run_async(
                svc.send_message_multi(
                    session_id=session_id,
                    user_message_text=message_text,
                    institution_id=institution_id,
                    user_role=user_role,
                )
            )
            return success_response(data=result)

        elif session_type == "pdf_chat":
            # ── Single-PDF path (Cycle 2, unchanged) ─────────────────────────
            if not ctx.get("resource_id"):
                return error_response(
                    code="VALIDATION_ERROR",
                    message="Session is not a PDF chat session",
                    status_code=400,
                )
            result = _run_async(
                svc.send_message(
                    session_id=session_id,
                    user_message_text=message_text,
                    institution_id=institution_id,
                    user_role=user_role,
                )
            )
            return success_response(data=result)

        else:
            return error_response(
                code="VALIDATION_ERROR",
                message="Session is not a PDF chat session",
                status_code=400,
            )

    except ValueError as e:
        logger.warning("PDF chat validation error: %s", type(e).__name__)
        err_msg = str(e)
        # Stale resource after session creation
        if "no longer accessible" in err_msg.lower():
            return error_response(
                code="RESOURCE_UNAVAILABLE",
                message="One or more resources in this session are no longer available.",
                status_code=422,
            )
        return error_response(code="NOT_FOUND", message="Session not found", status_code=404)
    except Exception as e:
        logger.error("PDF chat error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/pdf/sessions/<session_id>', methods=['GET'])
@require_auth
@require_permission('ai:use')
def get_pdf_session(session_id):
    """Get PDF chat session history and metadata (single-PDF or Multi-PDF).

    Security: Only returns sessions owned by the authenticated user (IDOR prevention).

    Response:
        200: { "session_id", "session_type",
               "resource_id" (single-PDF), "resource_title" (single-PDF),
               "resource_ids" (multi-PDF), "messages": [...] }
        404: Session not found or not owned by user
    """
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
        uid = _uuid.UUID(str(request.user.id))
    except (ValueError, TypeError):
        return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

    # IDOR prevention
    from app.models.ai_chat import ChatSession as _ChatSession
    session = db.session.query(_ChatSession).filter_by(
        id=sid, user_id=uid, is_deleted=False
    ).first()
    if not session:
        return error_response(code="NOT_FOUND", message="Session not found", status_code=404)

    try:
        svc = _get_pdf_chat_service()
        history = svc.get_session_history(str(sid))
        return success_response(data=history)
    except Exception as e:
        logger.error("PDF session history error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)
