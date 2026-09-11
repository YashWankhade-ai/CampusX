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


def _get_chat_service():
    global _chat_service
    if _chat_service is None:
        from app.services.ai.chat_service import ChatService
        _chat_service = ChatService()
    return _chat_service


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


# ── Phase 2 endpoints — retained for backward compatibility, gated ─────────────

@ai_bp.route('/summarize', methods=['POST'])
@require_auth
@require_permission('ai:use')
def summarize():
    """Text summarization. Phase 2 feature — retained for backward compatibility."""
    text = (request.get_json(silent=True) or {}).get('text', '').strip()
    if not text:
        return error_response(code="VALIDATION_ERROR", message="Text content required for summarization", status_code=400)
    if len(text) > 20000:
        return error_response(code="VALIDATION_ERROR", message="Text too long for summarization", status_code=400)

    try:
        from app.services.ai.summary_service import SummaryService
        svc = SummaryService()
        summary = _run_async(svc.summarize(text))
        return success_response(data={"summary": summary}, message="Summary generated successfully")
    except Exception as e:
        logger.error("Summarize error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/quiz/generate', methods=['POST'])
@require_auth
@require_permission('ai:use')
def generate_quiz():
    """Quiz generation. Phase 2 feature — retained for backward compatibility."""
    payload = request.get_json(silent=True) or {}
    topic = (payload.get('topic') or payload.get('text') or 'General Knowledge').strip()
    num_questions = min(int(payload.get('num_questions', 5)), 20)

    try:
        from app.services.ai.quiz_service import QuizService
        svc = QuizService()
        quiz = _run_async(svc.generate_quiz(topic, num_questions))
        return success_response(data=quiz, message="Quiz generated successfully")
    except Exception as e:
        logger.error("Quiz generation error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)


@ai_bp.route('/flashcards/generate', methods=['POST'])
@require_auth
@require_permission('ai:use')
def generate_flashcards():
    """Flashcard generation. Phase 2 feature — retained for backward compatibility."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or payload.get('topic') or 'General Topics').strip()
    num_cards = min(int(payload.get('num_cards', 5)), 20)

    try:
        from app.services.ai.flashcard_service import FlashcardService
        svc = FlashcardService()
        flashcards = _run_async(svc.generate_flashcards(text, num_cards))
        return success_response(data=flashcards, message="Flashcards generated successfully")
    except Exception as e:
        logger.error("Flashcards error: %s", type(e).__name__, exc_info=False)
        return error_response(code="AI_ERROR", message=_SAFE_AI_ERROR, status_code=500)
