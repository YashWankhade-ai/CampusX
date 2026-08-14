import json
import asyncio
from flask import Blueprint, request, Response, stream_with_context
from app.utils.response_utils import success_response, error_response
from app.services.ai.chat_service import ChatService
from app.services.ai.summary_service import SummaryService
from app.services.ai.quiz_service import QuizService
from app.services.ai.flashcard_service import FlashcardService
from app.middleware.auth import require_auth
from app.models.ai_chat import ChatSession
from app.extensions import db

ai_bp = Blueprint('ai', __name__)
chat_service = ChatService()
summary_service = SummaryService()
quiz_service = QuizService()
flashcard_service = FlashcardService()

@ai_bp.route('/sessions', methods=['POST'])
@require_auth
def create_session():
    title = (request.get_json() or {}).get('title', 'New Academic Chat')
    session = chat_service.create_session(user_id=request.user.id, title=title)
    return success_response(data={
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None
    }, status_code=201)

@ai_bp.route('/sessions', methods=['GET'])
@require_auth
def list_sessions():
    sessions = db.session.query(ChatSession).filter_by(user_id=request.user.id, is_deleted=False).order_by(ChatSession.created_at.desc()).all()
    res = [
        {
            "id": str(s.id),
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in sessions
    ]
    return success_response(data=res)

@ai_bp.route('/sessions/<session_id>', methods=['GET'])
@require_auth
def get_session(session_id):
    history = chat_service.get_session_history(session_id)
    return success_response(data={"session_id": session_id, "messages": history})

@ai_bp.route('/chat', methods=['POST'])
@require_auth
def chat():
    payload = request.get_json() or {}
    message_text = payload.get('message') or payload.get('prompt')
    session_id = payload.get('session_id')
    subject_id = payload.get('subject_id')

    if not message_text:
        return error_response(code="VALIDATION_ERROR", message="Message text is required", status_code=400)

    # Auto-create session if not provided
    if not session_id:
        sess = chat_service.create_session(user_id=request.user.id, title=message_text[:40])
        session_id = str(sess.id)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        res = loop.run_until_complete(
            chat_service.send_message(session_id=session_id, user_message_text=message_text, subject_id=subject_id)
        )
        return success_response(data=res)
    except Exception as e:
        return error_response(code="AI_ERROR", message=str(e), status_code=500)
    finally:
        loop.close()

@ai_bp.route('/chat/stream', methods=['POST'])
@require_auth
def chat_stream():
    payload = request.get_json() or {}
    message_text = payload.get('message') or payload.get('prompt')
    session_id = payload.get('session_id')
    subject_id = payload.get('subject_id')

    if not message_text:
        return error_response(code="VALIDATION_ERROR", message="Message text is required", status_code=400)

    if not session_id:
        sess = chat_service.create_session(user_id=request.user.id, title=message_text[:40])
        session_id = str(sess.id)

    def generate_sse():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            gen = chat_service.stream_message(session_id=session_id, user_message_text=message_text, subject_id=subject_id)
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    return Response(stream_with_context(generate_sse()), mimetype='text/event-stream')

@ai_bp.route('/summarize', methods=['POST'])
@require_auth
def summarize():
    text = (request.get_json() or {}).get('text')
    if not text:
        return error_response(code="VALIDATION_ERROR", message="Text content required for summarization", status_code=400)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        summary = loop.run_until_complete(summary_service.summarize(text))
        return success_response(data={"summary": summary}, message="Summary generated successfully")
    finally:
        loop.close()

@ai_bp.route('/quiz/generate', methods=['POST'])
@require_auth
def generate_quiz():
    payload = request.get_json() or {}
    topic = payload.get('topic') or payload.get('text', 'General Knowledge')
    num_questions = payload.get('num_questions', 5)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        quiz = loop.run_until_complete(quiz_service.generate_quiz(topic, num_questions))
        return success_response(data=quiz, message="Quiz generated successfully")
    finally:
        loop.close()

@ai_bp.route('/flashcards/generate', methods=['POST'])
@require_auth
def generate_flashcards():
    payload = request.get_json() or {}
    text = payload.get('text') or payload.get('topic', 'General Topics')
    num_cards = payload.get('num_cards', 5)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        flashcards = loop.run_until_complete(flashcard_service.generate_flashcards(text, num_cards))
        return success_response(data=flashcards, message="Flashcards generated successfully")
    finally:
        loop.close()
