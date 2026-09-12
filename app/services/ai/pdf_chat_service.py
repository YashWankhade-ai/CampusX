"""CampusX PDF Chat Service — document-grounded conversational Q&A.

Pipeline:
    validate_resource() → verify existence, approval, institution, deletion
    start_session()     → create ChatSession with context_data.resource_id
    send_message()      → scoped RAG (document_id filter) → LLM → citations → history

Security contract:
    - resource_id is validated against the DB at every request.
    - institution_id MUST come from the JWT (passed by blueprint) — never from client body.
    - Cross-institution access fails closed with 404 (no resource-existence leakage).
    - Only APPROVED, not-deleted resources can be chatted with.
    - Retrieved chunks are injected via RAG_CONTEXT_TEMPLATE (DATA fence).
    - Exception messages (str(exc)) are NEVER logged or returned to the client.

Conversation continuity:
    History is loaded from ChatMessage rows for the session, pruned to
    MAX_CONTEXT_TOKENS, and prepended to each LLM call. This gives basic
    follow-up question support (e.g. "Give me an example" after "What is DP?").

No duplicate models:
    Reuses ChatSession, ChatMessage, AICitation from app.models.ai_chat.
    resource_id is stored in ChatSession.context_data["resource_id"].
"""
import uuid
import logging
from typing import Optional, Dict, Any, List, Tuple

from app.extensions import db
from app.models.ai_chat import ChatSession, ChatMessage, AICitation
from app.models.resource import StudyMaterial
from app.models.user import User
from .clients import AIClients
from .rag_service import RAGService
from .chat_service import ChatService, estimate_tokens, MAX_CONTEXT_TOKENS
from .prompt_templates import (
    PDF_CHAT_SYSTEM_PROMPT,
    PDF_NO_CONTEXT_RESPONSE,
    RAG_CONTEXT_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Maximum characters per user message in PDF chat
MAX_PDF_MESSAGE_LEN = 2000

# Hard limit on conversation turns included in history (pairs)
MAX_HISTORY_TURNS = 10


class PDFChatService:
    """Document-grounded conversational AI for a single approved resource.

    Reuses RAGService with document_id filter and ChatService history/citation logic.
    Does NOT duplicate session management — ChatSession.context_data stores resource_id.
    """

    def __init__(
        self,
        ai_clients: Optional[AIClients] = None,
        rag_service: Optional[RAGService] = None,
    ):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.rag = rag_service if rag_service is not None else RAGService()
        # Reuse ChatService for session/history helpers
        self._chat_svc = ChatService(ai_clients=self.clients, rag_service=self.rag)

    # ── Resource validation ────────────────────────────────────────────────────

    def validate_resource(
        self,
        resource_id: str,
        institution_id: str,
    ) -> Tuple[Optional[StudyMaterial], Optional[str]]:
        """Validate that a resource is accessible for PDF chat.

        Security rules (all must pass):
            1. resource_id is a valid UUID.
            2. Resource exists in the DB.
            3. Resource is not soft-deleted.
            4. Resource status is APPROVED.
            5. Resource author belongs to the same institution as the requester.
               (Checked via StudyMaterial → author → User.institution_id join.)

        Returns:
            (StudyMaterial, None)        on success
            (None, error_code_string)    on failure

        Error codes:
            "INVALID_ID"        — resource_id is not a valid UUID
            "NOT_FOUND"         — resource does not exist or is deleted
            "NOT_APPROVED"      — resource exists but is not APPROVED
            "FORBIDDEN"         — resource belongs to a different institution

        Cross-institution policy:
            All failure cases other than "NOT_APPROVED" return "NOT_FOUND"
            to avoid leaking that a resource exists in another institution.
        """
        # 1. Parse UUID
        try:
            res_uuid = uuid.UUID(str(resource_id))
        except (ValueError, TypeError):
            return None, "INVALID_ID"

        # 2. Fetch from DB
        material = db.session.query(StudyMaterial).filter_by(id=res_uuid).first()
        if not material:
            return None, "NOT_FOUND"

        # 3. Soft-delete check
        if getattr(material, "is_deleted", False):
            return None, "NOT_FOUND"

        # 4. Institution isolation — join to author
        author = db.session.query(User).filter_by(id=material.author_id).first()
        if not author:
            return None, "NOT_FOUND"

        try:
            inst_uuid = uuid.UUID(str(institution_id)) if institution_id else None
        except (ValueError, TypeError):
            inst_uuid = None

        if inst_uuid is None or author.institution_id != inst_uuid:
            # Fail closed — return NOT_FOUND, not FORBIDDEN, to avoid cross-institution leakage
            return None, "NOT_FOUND"

        # 5. Approval check — only after institution check so we don't leak resource existence
        if material.status != "APPROVED":
            return None, "NOT_APPROVED"

        return material, None

    # ── Session management ─────────────────────────────────────────────────────

    def start_session(
        self,
        user_id: str,
        resource_id: str,
        resource_title: str = "Academic Document",
    ) -> ChatSession:
        """Create a PDF chat session bound to a specific resource.

        resource_id is stored in context_data so subsequent messages know
        which document to scope retrieval to. No schema migration needed —
        ChatSession.context_data is already a JSON column.
        """
        session = ChatSession(
            user_id=uuid.UUID(str(user_id)),
            title=f"PDF Chat: {resource_title[:180]}",
            context_data={
                "session_type": "pdf_chat",
                "resource_id": str(resource_id),
                "resource_title": resource_title,
                "created_by": "CampusX AI PDF Chat",
            },
        )
        db.session.add(session)
        db.session.commit()
        return session

    def get_session_resource_id(self, session: ChatSession) -> Optional[str]:
        """Extract the resource_id from a PDF chat session's context_data."""
        ctx = session.context_data or {}
        return ctx.get("resource_id")

    # ── Message sending ────────────────────────────────────────────────────────

    async def send_message(
        self,
        session_id: str,
        user_message_text: str,
        institution_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message in a PDF chat session.

        Security:
            - institution_id MUST come from the JWT (set by blueprint).
            - resource_id is re-read from ChatSession.context_data (DB), not client input.
            - RAG retrieval is scoped to the single resource_id + institution_id.
            - Citations are only saved for verified DB-resident materials.
            - No exception details are returned to the client.

        Conversation continuity:
            Previous messages in the session are loaded and prepended as history,
            pruned to MAX_CONTEXT_TOKENS to bound token usage.

        Returns:
            Dict with session_id, response, citations, confidence, model_used, usage.
        """
        session_uuid = uuid.UUID(str(session_id))
        session = db.session.query(ChatSession).filter_by(id=session_uuid).first()
        if not session:
            raise ValueError(f"Chat session {session_id} not found.")

        # Re-validate resource from session context — never from client input
        resource_id = self.get_session_resource_id(session)
        if not resource_id:
            raise ValueError("Session does not have an associated resource (not a PDF chat session).")

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
        # Prune to MAX_HISTORY_TURNS (pairs) then token budget
        if len(history_formatted) > MAX_HISTORY_TURNS * 2:
            history_formatted = history_formatted[-(MAX_HISTORY_TURNS * 2):]
        history_pruned = self._chat_svc._prune_conversation_history(history_formatted)

        # ── 3. PDF-scoped RAG retrieval ────────────────────────────────────────
        #    document_id restricts Qdrant and BM25 to this single resource.
        #    institution_id from JWT ensures no cross-institution leakage.
        context_text, sources = await self.rag.retrieve_context(
            query=user_message_text,
            institution=institution_id or "",
            document_id=resource_id,
            user_role=user_role,
        )

        # ── 4. Build system prompt ─────────────────────────────────────────────
        #    PDF_CHAT_SYSTEM_PROMPT is more restrictive than general Q&A:
        #    model is instructed to ONLY answer from document content.
        system_prompt = PDF_CHAT_SYSTEM_PROMPT
        if context_text:
            system_prompt += RAG_CONTEXT_TEMPLATE.format(context_text=context_text)

        history_pruned.append({"role": "user", "content": user_message_text})

        # ── 5. If no context, return a safe no-context response ───────────────
        if not context_text:
            ai_content = PDF_NO_CONTEXT_RESPONSE
            model_used = "no-retrieval-fallback"
            usage_data = {}
        else:
            # ── 6. Call LLM ────────────────────────────────────────────────────
            ai_response = await self.clients.call_claude(
                messages=history_pruned,
                system_prompt=system_prompt,
                model="claude-3-5-sonnet-20241022",
                institution_id=institution_id,
            )
            ai_content = ai_response.get("content", "")
            usage_data = ai_response.get("usage", {})
            model_used = ai_response.get("model", "claude-3-5-sonnet-20241022")

        # ── 7. Save AI response ────────────────────────────────────────────────
        ai_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="ai",
            content=ai_content,
            metadata_json={
                "model_used": model_used,
                "usage": usage_data,
                "sources_count": len(sources),
                "resource_id": resource_id,
            },
        )
        db.session.add(ai_msg)
        db.session.flush()

        # ── 8. Save citations — only verified DB-resident materials ────────────
        citations_created: List[Dict[str, Any]] = []
        for src in sources:
            mat_id_str = src.get("document_id")
            mat_uuid = None
            try:
                mat_uuid = uuid.UUID(mat_id_str) if mat_id_str else None
            except (ValueError, TypeError):
                pass

            if mat_uuid:
                mat_exists = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()
                if mat_exists:
                    cit = AICitation(
                        message_id=ai_msg.id,
                        study_material_id=mat_uuid,
                        chunk_index=src.get("chunk_index"),
                        excerpt=src.get("snippet", "")[:500],
                        relevance_score=src.get("score", 0.0),
                    )
                    db.session.add(cit)
                    citations_created.append({
                        "study_material_id": str(mat_uuid),
                        "title": mat_exists.title,
                        "chunk_index": src.get("chunk_index"),
                        "relevance_score": src.get("score", 0.0),
                        "excerpt": src.get("snippet", "")[:300],
                    })

        db.session.commit()

        top_score = sources[0].get("score", 0.0) if sources else 0.0
        confidence = self.rag.calculate_confidence(top_score)

        return {
            "session_id": str(session.id),
            "resource_id": resource_id,
            "user_message_id": str(user_msg.id),
            "ai_message_id": str(ai_msg.id),
            "response": ai_content,
            "model_used": model_used,
            "usage": usage_data,
            "citations": citations_created,
            "confidence": confidence,
        }

    # ── History retrieval ──────────────────────────────────────────────────────

    def get_session_history(self, session_id: str) -> Dict[str, Any]:
        """Get full PDF chat session with resource metadata and message history.

        Handles both single-PDF (resource_id) and Multi-PDF (resource_ids) sessions.
        """
        try:
            sid = uuid.UUID(str(session_id))
        except (ValueError, TypeError):
            return {}

        session = db.session.query(ChatSession).filter_by(id=sid).first()
        if not session:
            return {}

        ctx = session.context_data or {}
        messages = (
            db.session.query(ChatMessage)
            .filter_by(session_id=sid)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        return {
            "session_id": str(session.id),
            "title": session.title,
            # Single-PDF compat fields
            "resource_id": ctx.get("resource_id"),
            "resource_title": ctx.get("resource_title"),
            # Multi-PDF fields
            "resource_ids": ctx.get("resource_ids"),
            "session_type": ctx.get("session_type", "pdf_chat"),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "messages": [
                {
                    "id": str(m.id),
                    "sender_type": m.sender_type,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "metadata": m.metadata_json or {},
                }
                for m in messages
            ],
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Multi-PDF Chat extensions (Cycle 4)
    # ══════════════════════════════════════════════════════════════════════════

    # Maximum number of resources allowed per Multi-PDF Chat session.
    MAX_MULTI_PDF_RESOURCES = 10

    def validate_resources(
        self,
        resource_ids: List[str],
        institution_id: str,
    ) -> Tuple[List[StudyMaterial], Optional[str]]:
        """Validate a list of resource IDs for Multi-PDF Chat.

        Security rules:
            - resource_ids must be a non-empty list.
            - Maximum MAX_MULTI_PDF_RESOURCES entries.
            - Duplicate IDs are de-duplicated before validation (fail open for dups).
            - Every resource must pass all checks from validate_resource().
            - If ANY resource fails, the ENTIRE request is rejected (fail closed).
            - Cross-institution resources return NOT_FOUND (no existence leakage).

        Returns:
            (List[StudyMaterial], None)    on full success
            ([], error_code_string)        on any failure

        Error codes:
            "EMPTY_LIST"        — resource_ids is empty or not a list
            "TOO_MANY"          — more than MAX_MULTI_PDF_RESOURCES entries
            "INVALID_ID"        — any entry is not a valid UUID
            "NOT_FOUND"         — any resource not found / deleted / cross-institution
            "NOT_APPROVED"      — any resource exists but not APPROVED
        """
        if not isinstance(resource_ids, list) or len(resource_ids) == 0:
            return [], "EMPTY_LIST"

        # De-duplicate while preserving order, then check count
        seen = set()
        unique_ids = []
        for rid in resource_ids:
            key = str(rid).strip().lower()
            if key not in seen:
                seen.add(key)
                unique_ids.append(rid)

        if len(unique_ids) > self.MAX_MULTI_PDF_RESOURCES:
            return [], "TOO_MANY"

        validated = []
        for rid in unique_ids:
            material, err = self.validate_resource(rid, institution_id)
            if err is not None:
                # Fail closed — any failure rejects the complete request
                return [], err
            validated.append(material)

        return validated, None

    def start_multi_session(
        self,
        user_id: str,
        resource_ids: List[str],
        resource_titles: Optional[List[str]] = None,
    ) -> ChatSession:
        """Create a Multi-PDF chat session bound to multiple approved resources.

        Stores resource_ids list in context_data so subsequent messages can
        revalidate all resources from the DB — no migration required.

        context_data schema:
            {
                "session_type": "multi_pdf_chat",
                "resource_ids": ["uuid-1", "uuid-2", ...],
                "resource_count": N,
                "created_by": "CampusX AI Multi-PDF Chat",
            }
        """
        count = len(resource_ids)
        title = f"Multi-PDF Chat ({count} documents)"
        if resource_titles:
            joined = ", ".join(resource_titles[:3])
            suffix = " + more" if count > 3 else ""
            title = f"Multi-PDF Chat: {joined}{suffix}"

        session = ChatSession(
            user_id=uuid.UUID(str(user_id)),
            title=title[:200],
            context_data={
                "session_type": "multi_pdf_chat",
                "resource_ids": [str(r) for r in resource_ids],
                "resource_count": count,
                "created_by": "CampusX AI Multi-PDF Chat",
            },
        )
        db.session.add(session)
        db.session.commit()
        return session

    def get_session_resource_ids(self, session: ChatSession) -> Optional[List[str]]:
        """Extract resource_ids from a multi-PDF session's context_data.

        Returns None if the session is not a multi-PDF session.
        """
        ctx = session.context_data or {}
        if ctx.get("session_type") == "multi_pdf_chat":
            return ctx.get("resource_ids") or []
        return None

    async def send_message_multi(
        self,
        session_id: str,
        user_message_text: str,
        institution_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message in a Multi-PDF chat session.

        Security:
            - institution_id MUST come from the JWT (set by blueprint).
            - resource_ids are re-read from ChatSession.context_data (DB), never from client.
            - Every resource is revalidated per-request (handles post-session deletion).
            - If any resource becomes invalid, safe error returned — no partial retrieval.
            - RAG retrieval is scoped to validated resource_ids + institution_id.
            - Citations are only saved for verified DB-resident materials.
            - No exception details returned to the client.

        Conversation continuity:
            Previous messages are loaded, pruned to MAX_HISTORY_TURNS, and included.
        """
        session_uuid = uuid.UUID(str(session_id))
        session = db.session.query(ChatSession).filter_by(id=session_uuid).first()
        if not session:
            raise ValueError(f"Chat session {session_id} not found.")

        # Re-read resource_ids from DB — never trust client input
        resource_ids = self.get_session_resource_ids(session)
        if resource_ids is None or len(resource_ids) == 0:
            raise ValueError("Session does not have associated resources (not a multi-PDF session).")

        # ── Per-request revalidation of all resources ──────────────────────────
        # If any resource was deleted/unapproved after session creation, fail safely.
        validated_resources, val_err = self.validate_resources(resource_ids, institution_id or "")
        if val_err is not None:
            raise ValueError(f"One or more session resources are no longer accessible: {val_err}")

        validated_ids = [str(r.id) for r in validated_resources]

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
            for m in db_messages[:-1]
        ]
        if len(history_formatted) > MAX_HISTORY_TURNS * 2:
            history_formatted = history_formatted[-(MAX_HISTORY_TURNS * 2):]
        history_pruned = self._chat_svc._prune_conversation_history(history_formatted)

        # ── 3. Multi-document scoped RAG retrieval ─────────────────────────────
        #    document_ids restricts Qdrant (MatchAny) and BM25 (SQL IN) to the
        #    validated set. institution_id still enforced at the Qdrant layer.
        context_text, sources = await self.rag.retrieve_context(
            query=user_message_text,
            institution=institution_id or "",
            document_ids=validated_ids,
            user_role=user_role,
        )

        # ── 4. Build system prompt (same DATA fence as single-PDF chat) ────────
        from .prompt_templates import PDF_CHAT_SYSTEM_PROMPT, PDF_NO_CONTEXT_RESPONSE, RAG_CONTEXT_TEMPLATE
        system_prompt = PDF_CHAT_SYSTEM_PROMPT
        if context_text:
            system_prompt += RAG_CONTEXT_TEMPLATE.format(context_text=context_text)

        history_pruned.append({"role": "user", "content": user_message_text})

        # ── 5. If no context, return safe no-context response ─────────────────
        if not context_text:
            ai_content = PDF_NO_CONTEXT_RESPONSE
            model_used = "no-retrieval-fallback"
            usage_data = {}
        else:
            # ── 6. Call LLM ────────────────────────────────────────────────────
            ai_response = await self.clients.call_claude(
                messages=history_pruned,
                system_prompt=system_prompt,
                model="claude-3-5-sonnet-20241022",
                institution_id=institution_id,
            )
            ai_content = ai_response.get("content", "")
            usage_data = ai_response.get("usage", {})
            model_used = ai_response.get("model", "claude-3-5-sonnet-20241022")

        # ── 7. Save AI response ────────────────────────────────────────────────
        ai_msg = ChatMessage(
            session_id=session_uuid,
            sender_type="ai",
            content=ai_content,
            metadata_json={
                "model_used": model_used,
                "usage": usage_data,
                "sources_count": len(sources),
                "resource_ids": validated_ids,
            },
        )
        db.session.add(ai_msg)
        db.session.flush()

        # ── 8. Save citations — only verified DB-resident materials ────────────
        citations_created: List[Dict[str, Any]] = []
        for src in sources:
            mat_id_str = src.get("document_id")
            mat_uuid = None
            try:
                mat_uuid = uuid.UUID(mat_id_str) if mat_id_str else None
            except (ValueError, TypeError):
                pass

            if mat_uuid:
                mat_exists = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()
                if mat_exists:
                    cit = AICitation(
                        message_id=ai_msg.id,
                        study_material_id=mat_uuid,
                        chunk_index=src.get("chunk_index"),
                        excerpt=src.get("snippet", "")[:500],
                        relevance_score=src.get("score", 0.0),
                    )
                    db.session.add(cit)
                    citations_created.append({
                        "study_material_id": str(mat_uuid),
                        "title": mat_exists.title,
                        "chunk_index": src.get("chunk_index"),
                        "relevance_score": src.get("score", 0.0),
                        "excerpt": src.get("snippet", "")[:300],
                    })

        db.session.commit()

        top_score = sources[0].get("score", 0.0) if sources else 0.0
        confidence = self.rag.calculate_confidence(top_score)

        return {
            "session_id": str(session.id),
            "resource_ids": validated_ids,
            "user_message_id": str(user_msg.id),
            "ai_message_id": str(ai_msg.id),
            "response": ai_content,
            "model_used": model_used,
            "usage": usage_data,
            "citations": citations_created,
            "confidence": confidence,
        }

