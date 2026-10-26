"""CampusX AI Chat Service — session-based Q&A with RAG.

Security contract:
    - institution_id MUST come from the JWT-verified request (passed by blueprint).
    - It is NEVER read from client-supplied message content inside this service.
    - Retrieved document text is injected into the prompt via RAG_CONTEXT_TEMPLATE,
      which structurally separates DATA from system instructions.
    - Exception messages (str(exc)) are NEVER logged or returned to the client.
      Only type(exc).__name__ is used to avoid leaking API keys or tracebacks.

Quality layer (Cycle 5):
    - CitationVerifier   — all citations verified against DB before saving.
    - ConfidenceScorer   — multi-signal 0.0–1.0 score + level.
    - GroundingVerifier  — SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED.
    - PromptSafetyGuard  — injection-pattern detection + DATA-fence labeling.
"""
import uuid
import json
import logging
from typing import Optional, AsyncGenerator, List, Dict, Any

from app.extensions import db
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.resource import StudyMaterial
from .clients import AIClients
from .rag_service import RAGService
from .prompt_templates import SYSTEM_TUTOR_PROMPT, RAG_CONTEXT_TEMPLATE
from .citation_verifier import CitationVerifier
from .confidence_scorer import ConfidenceScorer
from .grounding_verifier import GroundingVerifier
from .prompt_safety import PromptSafetyGuard

logger = logging.getLogger(__name__)

MAX_CONTEXT_TOKENS = 4000


def estimate_tokens(text: str) -> int:
    """Approximate token count (1 token ≈ 4 chars). For context-window pruning only."""
    return len(text) // 4 + 1


class ChatService:
    def __init__(
        self,
        ai_clients: Optional[AIClients] = None,
        rag_service: Optional[RAGService] = None,
        citation_verifier: Optional[CitationVerifier] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        grounding_verifier: Optional[GroundingVerifier] = None,
        prompt_safety_guard: Optional[PromptSafetyGuard] = None,
    ):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.rag = rag_service if rag_service is not None else RAGService()
        self.citation_verifier = citation_verifier if citation_verifier is not None else CitationVerifier()
        self.confidence_scorer = confidence_scorer if confidence_scorer is not None else ConfidenceScorer()
        self.grounding_verifier = grounding_verifier if grounding_verifier is not None else GroundingVerifier()
        self.prompt_safety_guard = prompt_safety_guard if prompt_safety_guard is not None else PromptSafetyGuard()

    # ── Session management ─────────────────────────────────────────────────────

    def create_session(self, user_id: str, title: str = "New AI Conversation") -> ChatSession:
        session = ChatSession(
            user_id=uuid.UUID(str(user_id)),
            title=title.strip(),
            context_data={"created_by": "CampusX AI"},
        )
        db.session.add(session)
        db.session.commit()
        return session

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        session = db.session.query(ChatSession).filter_by(
            id=uuid.UUID(str(session_id))
        ).first()
        if not session:
            return []

        return [
            {
                "id": str(msg.id),
                "sender_type": msg.sender_type,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "metadata": msg.metadata_json or {},
            }
            for msg in session.messages
        ]

    # ── Conversation history management ───────────────────────────────────────

    def _prune_conversation_history(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> List[Dict[str, str]]:
        """Drop oldest user-assistant pairs when total token estimate exceeds max_tokens."""
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        pruned = list(messages)
        while total_tokens > max_tokens and len(pruned) > 2:
            pruned.pop(0)
            if pruned:
                pruned.pop(0)
            total_tokens = sum(estimate_tokens(m.get("content", "")) for m in pruned)
        return pruned

    # ── Core message handler ───────────────────────────────────────────────────

    async def send_message(
        self,
        session_id: str,
        user_message_text: str,
        subject_id: Optional[str] = None,
        institution_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a user message, retrieve RAG context, call LLM, save history & citations.

        Security:
            institution_id MUST come from the JWT-verified request (set by blueprint).
            It is NEVER read from client-supplied input here.

        Quality layer (Cycle 5):
            - PromptSafetyGuard scans context for injection patterns before LLM call.
            - CitationVerifier validates each citation against DB (5-point check).
            - GroundingVerifier classifies answer support (SUPPORTED / PARTIAL / UNSUPPORTED).
            - ConfidenceScorer computes multi-signal 0.0–1.0 score + level.
        """
        session_uuid = uuid.UUID(str(session_id))
        session = db.session.query(ChatSession).filter_by(id=session_uuid).first()
        if not session:
            raise ValueError(f"Chat session {session_id} not found.")

        # ── 1. Save user message ───────────────────────────────────────────────
        user_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="user",
            content=user_message_text,
        )
        db.session.add(user_msg)
        db.session.flush()

        # ── 2. Build pruned conversation history ───────────────────────────────
        db_messages = (
            db.session.query(ChatMessage)
            .filter_by(session_id=session_uuid)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        history_formatted = [
            {
                "role": "user" if m.sender_type == "user" else "assistant",
                "content": m.content,
            }
            for m in db_messages[:-1]  # exclude the just-saved user message
        ]
        history_pruned = self._prune_conversation_history(history_formatted)

        # ── 3. Retrieve RAG context — institution-scoped, approved-only ────────
        #    institution_id comes from JWT (set by blueprint). Never from client.
        context_text, sources = await self.rag.retrieve_context(
            query=user_message_text,
            institution=institution_id or "",
            subject=subject_id or "",
            user_role=user_role,
        )

        # ── 4. Prompt safety scan (Cycle 5) ───────────────────────────────────
        #    Scans retrieved content for injection patterns and adds warning header.
        #    Academic content is PRESERVED — we label it, never discard it.
        safe_context, injection_detected = self.prompt_safety_guard.scan_and_label(context_text)

        # ── 5. Build system prompt with DATA fence ─────────────────────────────
        #    Retrieved documents are injected via RAG_CONTEXT_TEMPLATE — a
        #    structurally separate DATA section — NOT concatenated into the
        #    system instruction text itself. This is the prompt-injection
        #    defense-in-depth boundary. PromptSafetyGuard provides layer 2.
        system_prompt = SYSTEM_TUTOR_PROMPT
        if safe_context:
            system_prompt += RAG_CONTEXT_TEMPLATE.format(context_text=safe_context)

        history_pruned.append({"role": "user", "content": user_message_text})

        # ── 6. Call LLM (Claude primary, OpenAI fallback, mock final fallback) ─
        ai_response = await self.clients.call_claude(
            messages=history_pruned,
            system_prompt=system_prompt,
            model="claude-3-5-sonnet-20241022",
            institution_id=institution_id,
        )

        ai_content = ai_response.get("content", "")
        usage_data = ai_response.get("usage", {})
        model_used = ai_response.get("model", "claude-3-5-sonnet-20241022")

        # ── 7. Grounding verification (Cycle 5) ───────────────────────────────
        try:
            grounding_status = self.grounding_verifier.verify(
                answer=ai_content,
                context=context_text,
                grounding_available=bool(context_text),
            )
        except Exception:
            grounding_status = None  # Fail safe — never block primary response

        # ── 8. Save AI response message ────────────────────────────────────────
        ai_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="ai",
            content=ai_content,
            metadata_json={
                "model_used": model_used,
                "usage": usage_data,
                "tool_calls": ai_response.get("tool_calls", []),
                "sources_count": len(sources),
                "grounding_status": grounding_status,
                "injection_detected": injection_detected,
            },
        )
        db.session.add(ai_msg)
        db.session.flush()

        # ── 9. Citation verification (Cycle 5) ────────────────────────────────
        #    All citations verified against DB: existence + not-deleted + APPROVED
        #    + institution match. Fabricated or cross-institution citations dropped.
        verified_citations = self.citation_verifier.verify_citations(
            raw_sources=sources,
            institution_id=institution_id or "",
        )

        citations_created: List[Dict[str, Any]] = []
        for vc in verified_citations:
            mat_uuid = uuid.UUID(vc["study_material_id"])
            cit = AICitation(
                message_id=ai_msg.id,
                study_material_id=mat_uuid,
                chunk_index=vc.get("chunk_index"),
                excerpt=vc.get("excerpt", "")[:500],
                relevance_score=vc.get("relevance_score", 0.0),
            )
            db.session.add(cit)
            citations_created.append({
                "document_id": vc["study_material_id"],
                "study_material_id": vc["study_material_id"],
                "title": vc["title"],
                "chunk_index": vc.get("chunk_index"),
                "relevance_score": vc.get("relevance_score", 0.0),
                "excerpt": vc.get("excerpt_short", ""),
            })

        db.session.commit()

        # ── 10. Confidence scoring (Cycle 5) ──────────────────────────────────
        #    Multi-signal score: top/avg RRF score + chunk count + diversity + grounding.
        #    Also preserve legacy HIGH/MEDIUM/LOW label for backward compatibility.
        confidence_result = self.confidence_scorer.score(
            sources=verified_citations or sources,
            grounding_status=grounding_status,
        )
        top_score = sources[0].get("score", 0.0) if sources else 0.0
        confidence = self.rag.calculate_confidence(top_score)   # backward compat

        return {
            "session_id": str(session.id),
            "user_message_id": str(user_msg.id),
            "ai_message_id": str(ai_msg.id),
            "response": ai_content,
            "model_used": model_used,
            "usage": usage_data,
            "citations": citations_created,
            # ── Cycle 5 quality fields ────────────────────────────────────────
            "confidence": confidence,                              # backward compat: HIGH/MEDIUM/LOW/NONE
            "confidence_score": confidence_result["score"],        # new: 0.0–1.0 float
            "confidence_level": confidence_result["level"],        # new: low/medium/high
            "grounding_status": grounding_status,                  # new: SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED
        }


    # ── SSE streaming ──────────────────────────────────────────────────────────

    async def stream_message(
        self,
        session_id: str,
        user_message_text: str,
        subject_id: Optional[str] = None,
        institution_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE response chunks.

        Calls send_message() internally — streaming is simulated word-by-word
        from the completed response. True token streaming requires async LLM
        streaming support (Phase 2).
        """
        res = await self.send_message(
            session_id=session_id,
            user_message_text=user_message_text,
            subject_id=subject_id,
            institution_id=institution_id,
            user_role=user_role,
        )
        words = res["response"].split(" ")

        for i, word in enumerate(words):
            chunk = json.dumps(
                {"delta": word + (" " if i < len(words) - 1 else ""), "done": False}
            )
            yield f"data: {chunk}\n\n"

        final_payload = json.dumps({
            "delta": "",
            "done": True,
            "session_id": res["session_id"],
            "model_used": res["model_used"],
            "usage": res["usage"],
            "citations": res["citations"],
            "confidence": res["confidence"],
        })
        yield f"data: {final_payload}\n\n"
