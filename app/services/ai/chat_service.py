import uuid
import json
from typing import Optional, AsyncGenerator, List, Dict, Any
from app.extensions import db
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.resource import StudyMaterial
from .clients import AIClients
from .rag_service import RAGService
from .prompt_templates import SYSTEM_TUTOR_PROMPT, RAG_ANSWER_PROMPT

MAX_CONTEXT_TOKENS = 4000

def estimate_tokens(text: str) -> int:
    """Approximate token count (1 token ~= 4 chars)."""
    return len(text) // 4 + 1

class ChatService:
    def __init__(self, ai_clients: Optional[AIClients] = None, rag_service: Optional[RAGService] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.rag = rag_service if rag_service is not None else RAGService()

    def create_session(self, user_id: str, title: str = "New AI Conversation") -> ChatSession:
        session = ChatSession(
            user_id=uuid.UUID(str(user_id)),
            title=title.strip(),
            context_data={"created_by": "CampusX AI"}
        )
        db.session.add(session)
        db.session.commit()
        return session

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        session = db.session.query(ChatSession).filter_by(id=uuid.UUID(str(session_id))).first()
        if not session:
            return []

        history = []
        for msg in session.messages:
            history.append({
                "id": str(msg.id),
                "sender_type": msg.sender_type,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "metadata": msg.metadata_json or {}
            })
        return history

    def _prune_conversation_history(self, messages: List[Dict[str, str]], max_tokens: int = MAX_CONTEXT_TOKENS) -> List[Dict[str, str]]:
        """
        Prunes oldest conversation history turns when total token estimate exceeds max_tokens.
        """
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        pruned = list(messages)
        while total_tokens > max_tokens and len(pruned) > 2:
            # Drop oldest user-assistant pair
            pruned.pop(0)
            if pruned:
                pruned.pop(0)
            total_tokens = sum(estimate_tokens(m.get("content", "")) for m in pruned)
        return pruned

    async def send_message(self, session_id: str, user_message_text: str, subject_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send user message, execute RAG vector search, call Claude Sonnet (fallback to OpenAI), and save history & citations.
        """
        session_uuid = uuid.UUID(str(session_id))
        session = db.session.query(ChatSession).filter_by(id=session_uuid).first()
        if not session:
            raise ValueError(f"Chat session {session_id} not found.")

        # 1. Save User Message
        user_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="user",
            content=user_message_text
        )
        db.session.add(user_msg)
        db.session.flush()

        # 2. Build Conversation History & Context Window Management
        db_messages = db.session.query(ChatMessage).filter_by(session_id=session_uuid).order_by(ChatMessage.created_at.asc()).all()
        history_formatted = [
            {"role": "user" if m.sender_type == "user" else "assistant", "content": m.content}
            for m in db_messages[:-1] # exclude current user message to format cleanly
        ]
        history_pruned = self._prune_conversation_history(history_formatted)

        # 3. Retrieve RAG Reference Material & Context
        context_text, sources = await self.rag.retrieve_context(query=user_message_text, institution="", subject=subject_id or "")

        # Prepare System & User Prompts
        system_prompt = SYSTEM_TUTOR_PROMPT
        if context_text:
            system_prompt += f"\n\n--- REFERENCE STUDY MATERIAL ---\n{context_text}\n---------------------------------"

        history_pruned.append({"role": "user", "content": user_message_text})

        # 4. Execute Multi-Provider LLM Call (Claude Sonnet primary -> OpenAI fallback)
        ai_response = await self.clients.call_claude(
            messages=history_pruned,
            system_prompt=system_prompt,
            model="claude-3-5-sonnet-20241022"
        )

        ai_content = ai_response.get("content", "")
        usage_data = ai_response.get("usage", {})
        model_used = ai_response.get("model", "claude-3-5-sonnet-20241022")

        # 5. Save AI Response Message
        ai_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="ai",
            content=ai_content,
            metadata_json={
                "model_used": model_used,
                "usage": usage_data,
                "tool_calls": ai_response.get("tool_calls", []),
                "sources_count": len(sources)
            }
        )
        db.session.add(ai_msg)
        db.session.flush()

        # 6. Save Citations
        citations_created = []
        for src in sources:
            mat_id_str = src.get("document_id")
            try:
                mat_uuid = uuid.UUID(mat_id_str) if mat_id_str else None
            except Exception:
                mat_uuid = None

            if mat_uuid:
                mat_exists = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()
                if mat_exists:
                    cit = AICitation(
                        message_id=ai_msg.id,
                        study_material_id=mat_uuid,
                        excerpt=src.get("snippet", "")[:500],
                        relevance_score=src.get("score", 0.0)
                    )
                    db.session.add(cit)
                    citations_created.append({
                        "study_material_id": str(mat_uuid),
                        "title": mat_exists.title,
                        "relevance_score": src.get("score", 0.0)
                    })

        db.session.commit()

        return {
            "session_id": str(session.id),
            "user_message_id": str(user_msg.id),
            "ai_message_id": str(ai_msg.id),
            "response": ai_content,
            "model_used": model_used,
            "usage": usage_data,
            "citations": citations_created
        }

    async def stream_message(self, session_id: str, user_message_text: str, subject_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        Stream SSE response data chunks to the client.
        """
        # Execute message send and stream chunks
        res = await self.send_message(session_id=session_id, user_message_text=user_message_text, subject_id=subject_id)
        words = res["response"].split(" ")

        for i, word in enumerate(words):
            chunk = json.dumps({"delta": word + (" " if i < len(words) - 1 else ""), "done": False})
            yield f"data: {chunk}\n\n"

        final_payload = json.dumps({
            "delta": "",
            "done": True,
            "session_id": res["session_id"],
            "model_used": res["model_used"],
            "usage": res["usage"],
            "citations": res["citations"]
        })
        yield f"data: {final_payload}\n\n"
