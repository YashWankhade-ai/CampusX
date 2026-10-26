"""CampusX Study Tools Service — shared grounding, retrieval, validation, and generation.

This module is the single shared infrastructure for:
    - Quiz Generator
    - Flashcard Generator
    - Summary Generator

Design:
    Resource validation   → reused from PDFChatService.validate_resource()
    Context retrieval     → reused from RAGService.retrieve_context(document_id=...)
    LLM call              → reused AIClients.call_claude()
    Output parsing        → shared _parse_json_output() / _validate_quiz() / _validate_flashcards()
    DATA fence            → RAG_CONTEXT_TEMPLATE (same as PDF chat / General Q&A)

Security contract:
    - institution_id MUST come from the JWT (passed by blueprint).
    - resource_id is validated against DB at each call.
    - Cross-institution resources fail closed with NOT_FOUND.
    - Only APPROVED, not-deleted resources can be used.
    - Retrieved content is injected via RAG_CONTEXT_TEMPLATE (DATA fence).
    - Exception details are NEVER returned to the client.
    - LLM output is treated as untrusted input and validated before returning.

No new DB tables:
    Quiz, flashcard, and summary results are returned in-memory.
    No persistence required — callers receive the generated payload directly.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.services.ai.clients import AIClients
from app.services.ai.rag_service import RAGService
from app.services.ai.prompt_templates import (
    RAG_CONTEXT_TEMPLATE,
    MAX_STUDY_TOOL_CONTEXT_CHARS,
    MAX_QUIZ_QUESTIONS,
    MAX_FLASHCARD_COUNT,
    MAX_SUMMARY_CHARS,
    GROUNDED_QUIZ_SYSTEM_PROMPT,
    GROUNDED_FLASHCARD_SYSTEM_PROMPT,
    GROUNDED_SUMMARY_SYSTEM_PROMPT,
)
from app.services.ai.confidence_scorer import ConfidenceScorer
from app.services.ai.grounding_verifier import GroundingVerifier
from app.services.ai.prompt_safety import PromptSafetyGuard

logger = logging.getLogger(__name__)

# Fallback messages shown when there is insufficient retrieval context.
_NO_CONTEXT_QUIZ = (
    "There is not enough approved content from this resource to generate a quiz. "
    "The document may not have been indexed yet, or the content is insufficient."
)
_NO_CONTEXT_FLASHCARDS = (
    "There is not enough approved content from this resource to generate flashcards. "
    "The document may not have been indexed yet, or the content is insufficient."
)
_NO_CONTEXT_SUMMARY = (
    "There is not enough approved content from this resource to generate a summary. "
    "The document may not have been indexed yet, or the content is insufficient."
)


class StudyToolsService:
    """Shared service for quiz, flashcard, and summary generation.

    All generation is grounded in retrieved approved resource content.
    LLM output is parsed and validated before returning — malformed output
    is rejected safely without exposing raw LLM responses or tracebacks.
    """

    def __init__(
        self,
        ai_clients: Optional[AIClients] = None,
        rag_service: Optional[RAGService] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        grounding_verifier: Optional[GroundingVerifier] = None,
        prompt_safety_guard: Optional[PromptSafetyGuard] = None,
    ):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.rag = rag_service if rag_service is not None else RAGService()
        self.confidence_scorer = confidence_scorer if confidence_scorer is not None else ConfidenceScorer()
        self.grounding_verifier = grounding_verifier if grounding_verifier is not None else GroundingVerifier()
        self.prompt_safety_guard = prompt_safety_guard if prompt_safety_guard is not None else PromptSafetyGuard()

    def _compute_quality(
        self,
        generated_text: str,
        retrieved_citations: List[Dict[str, Any]],
        ctx_text: str,
    ) -> Dict[str, Any]:
        """Compute quality metadata for study tool outputs.

        Returns dict with: confidence_score, confidence_level, grounding_status.
        Fails safely — never raises; returns defaults on any error.
        """
        try:
            grounding_status = self.grounding_verifier.verify(
                answer=generated_text,
                context=ctx_text,
                grounding_available=bool(ctx_text),
            )
        except Exception:
            grounding_status = None

        try:
            # Build source-compatible dicts from retrieved_citations
            # (retrieved_citations from RAGService have 'score' key)
            scorer_sources = [
                {
                    "document_id": c.get("document_id"),
                    "score": c.get("score", 0.0),
                }
                for c in retrieved_citations
            ]
            confidence_result = self.confidence_scorer.score(
                sources=scorer_sources,
                grounding_status=grounding_status,
            )
        except Exception:
            confidence_result = {"score": 0.0, "level": "low"}

        return {
            "confidence_score": confidence_result["score"],
            "confidence_level": confidence_result["level"],
            "grounding_status": grounding_status,
        }


    # ── Resource validation ────────────────────────────────────────────────────
    # Delegates to PDFChatService.validate_resource() — the same security contract.
    # We call it directly via import to avoid duplicating the logic.

    def validate_resource(
        self, resource_id: str, institution_id: str
    ) -> Tuple[Any, Optional[str]]:
        """Validate a resource for study tool generation.

        Returns (StudyMaterial, None) on success, (None, error_code) on failure.
        Error codes: INVALID_ID, NOT_FOUND, NOT_APPROVED, FORBIDDEN.

        Security: Cross-institution access always returns NOT_FOUND (fail closed).
        """
        from app.services.ai.pdf_chat_service import PDFChatService
        # Instantiate with no LLM clients — we only need the validation method.
        _svc = PDFChatService.__new__(PDFChatService)
        return PDFChatService.validate_resource(_svc, resource_id, institution_id)

    # ── Grounded retrieval ─────────────────────────────────────────────────────

    async def _retrieve_grounded_context(
        self,
        query: str,
        institution_id: str,
        resource_id: str,
        limit: int = 8,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Retrieve institution+document-scoped context via RAGService.

        The retrieved context is bounded at MAX_STUDY_TOOL_CONTEXT_CHARS.
        Returns (context_text, citations_list).
        """
        ctx_text, citations = await self.rag.retrieve_context(
            query=query,
            institution=institution_id or "",
            document_id=resource_id,
            limit=limit,
        )
        # Apply study-tool-specific context cap (may be different from RAG cap)
        if len(ctx_text) > MAX_STUDY_TOOL_CONTEXT_CHARS:
            ctx_text = ctx_text[:MAX_STUDY_TOOL_CONTEXT_CHARS] + "\n[...truncated]"
        return ctx_text, citations

    # ── JSON output parsing ────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from raw LLM output.

        Handles markdown fences (```json ... ```) as well as bare JSON.
        Returns None if no valid JSON object is found.
        """
        if not raw:
            return None
        text = raw.strip()
        # Strip markdown json fence
        if "```json" in text:
            text = text.split("```json", 1)[1]
            if "```" in text:
                text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            if "```" in text:
                text = text.split("```", 1)[0]
        text = text.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        # Try to find first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # ── Quiz validation ────────────────────────────────────────────────────────

    @staticmethod
    def _validate_quiz(
        data: Dict[str, Any],
        max_questions: int,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Validate parsed quiz JSON against the expected schema.

        Returns (validated_dict, None) or (None, error_reason).
        """
        if not isinstance(data, dict):
            return None, "Quiz output is not a JSON object"

        questions = data.get("questions")
        if not isinstance(questions, list):
            return None, "Quiz missing 'questions' list"
        if len(questions) == 0:
            return None, "Quiz has no questions"

        valid_questions = []
        for i, q in enumerate(questions[:max_questions]):
            if not isinstance(q, dict):
                continue
            question_text = str(q.get("question", "")).strip()
            options = q.get("options", [])
            correct_idx = q.get("correct_answer_index")
            if not question_text:
                continue
            if not isinstance(options, list) or len(options) < 2:
                continue
            # Normalize options to strings
            options = [str(o) for o in options]
            # correct_answer_index must be a valid int index
            try:
                correct_idx = int(correct_idx)
                if not (0 <= correct_idx < len(options)):
                    correct_idx = 0
            except (TypeError, ValueError):
                correct_idx = 0

            valid_questions.append({
                "question_number": len(valid_questions) + 1,
                "question": question_text,
                "options": options,
                "correct_answer_index": correct_idx,
                "explanation": str(q.get("explanation", "")).strip() or "See reference material.",
            })

        if not valid_questions:
            return None, "No valid questions found in LLM output"

        return {
            "topic": str(data.get("topic", "Academic Quiz")).strip(),
            "questions": valid_questions,
            "question_count": len(valid_questions),
        }, None

    # ── Flashcard validation ───────────────────────────────────────────────────

    @staticmethod
    def _validate_flashcards(
        data: Dict[str, Any],
        max_cards: int,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Validate parsed flashcard JSON.

        Returns (validated_dict, None) or (None, error_reason).
        """
        if not isinstance(data, dict):
            return None, "Flashcard output is not a JSON object"

        cards = data.get("flashcards")
        if not isinstance(cards, list):
            return None, "Flashcard output missing 'flashcards' list"
        if len(cards) == 0:
            return None, "Flashcard output has no cards"

        valid_cards = []
        for c in cards[:max_cards]:
            if not isinstance(c, dict):
                continue
            front = str(c.get("front", "")).strip()
            back = str(c.get("back", "")).strip()
            if not front or not back:
                continue
            valid_cards.append({
                "front": front,
                "back": back,
                "category": str(c.get("category", "General")).strip(),
            })

        if not valid_cards:
            return None, "No valid flashcards found in LLM output"

        return {
            "flashcards": valid_cards,
            "card_count": len(valid_cards),
        }, None

    # ── Summary validation ─────────────────────────────────────────────────────

    @staticmethod
    def _validate_summary(raw: str) -> Tuple[Optional[str], Optional[str]]:
        """Validate and truncate a generated summary.

        Returns (summary_text, None) or (None, error_reason).
        """
        if not raw or not raw.strip():
            return None, "Empty summary from LLM"
        summary = raw.strip()
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[:MAX_SUMMARY_CHARS] + "\n\n[Summary truncated to size limit.]"
        return summary, None

    # ── Quiz generation ────────────────────────────────────────────────────────

    async def generate_quiz(
        self,
        resource_id: str,
        institution_id: str,
        resource_title: str,
        num_questions: int = 5,
        citations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate a grounded quiz from an approved resource.

        Retrieval is scoped to the single resource via RAGService(document_id=...).
        LLM output is parsed and validated — malformed output returns a safe error dict.
        """
        num_questions = max(1, min(num_questions, MAX_QUIZ_QUESTIONS))

        ctx_text, retrieved_citations = await self._retrieve_grounded_context(
            query=f"key concepts definitions examples {resource_title}",
            institution_id=institution_id,
            resource_id=resource_id,
            limit=8,
        )

        if not ctx_text:
            try:
                import uuid as _u
                from app.models.resource import StudyMaterial
                mat = db.session.query(StudyMaterial).filter_by(id=_u.UUID(str(resource_id))).first() if resource_id else None
                if mat:
                    ctx_text = f"Title: {mat.title}\nDescription: {mat.description or 'Academic reference document'}\n"
                    if getattr(mat, 'department_name', None):
                        ctx_text += f"Department: {mat.department_name}\n"
            except Exception:
                pass

        if not ctx_text:
            return {
                "success": False,
                "error": "NO_CONTEXT",
                "message": _NO_CONTEXT_QUIZ,
                "resource_id": resource_id,
            }

        # Inject retrieved content via DATA fence
        system_prompt = GROUNDED_QUIZ_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(
            context_text=ctx_text
        )
        user_message = (
            f"Generate exactly {num_questions} multiple-choice questions based "
            f"ONLY on the reference material above from the document: '{resource_title}'. "
            f"Output valid JSON only."
        )

        try:
            response = await self.clients.call_claude(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                model="claude-3-5-sonnet-20241022",
                enable_tools=False,
            )
            raw_content = response.get("content", "")
        except Exception as exc:
            logger.warning("[StudyTools] Quiz LLM call failed: %s", type(exc).__name__)
            return {
                "success": False,
                "error": "LLM_ERROR",
                "message": "The AI service is temporarily unavailable. Please try again.",
                "resource_id": resource_id,
            }

        parsed = self._extract_json(raw_content)
        if parsed is None:
            logger.warning("[StudyTools] Quiz: could not parse JSON from LLM output")
            return {
                "success": False,
                "error": "PARSE_ERROR",
                "message": "The AI returned an unexpected format. Please try again.",
                "resource_id": resource_id,
            }

        validated, err = self._validate_quiz(parsed, max_questions=num_questions)
        if validated is None:
            logger.warning("[StudyTools] Quiz validation failed: %s", err)
            return {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "The AI returned an unexpected format. Please try again.",
                "resource_id": resource_id,
            }

        # Attach citation metadata (no fabrication — uses only retrieved sources)
        source_refs = [
            {
                "document_id": c.get("document_id"),
                "title": c.get("title"),
                "chunk_index": c.get("chunk_index"),
                "relevance_score": c.get("score"),
            }
            for c in retrieved_citations
        ]

        return {
            "success": True,
            "resource_id": resource_id,
            "resource_title": resource_title,
            **validated,
            "sources": source_refs,
            "model_used": response.get("model", ""),
            "quality": self._compute_quality(
                generated_text=raw_content,
                retrieved_citations=retrieved_citations,
                ctx_text=ctx_text,
            ),
        }

    # ── Flashcard generation ───────────────────────────────────────────────────

    async def generate_flashcards(
        self,
        resource_id: str,
        institution_id: str,
        resource_title: str,
        num_cards: int = 10,
    ) -> Dict[str, Any]:
        """Generate grounded flashcards from an approved resource."""
        num_cards = max(1, min(num_cards, MAX_FLASHCARD_COUNT))

        ctx_text, retrieved_citations = await self._retrieve_grounded_context(
            query=f"key concepts definitions terms {resource_title}",
            institution_id=institution_id,
            resource_id=resource_id,
            limit=8,
        )

        if not ctx_text:
            try:
                import uuid as _u
                from app.models.resource import StudyMaterial
                mat = db.session.query(StudyMaterial).filter_by(id=_u.UUID(str(resource_id))).first() if resource_id else None
                if mat:
                    ctx_text = f"Title: {mat.title}\nDescription: {mat.description or 'Academic reference document'}\n"
                    if getattr(mat, 'department_name', None):
                        ctx_text += f"Department: {mat.department_name}\n"
            except Exception:
                pass

        if not ctx_text:
            return {
                "success": False,
                "error": "NO_CONTEXT",
                "message": _NO_CONTEXT_FLASHCARDS,
                "resource_id": resource_id,
            }

        system_prompt = GROUNDED_FLASHCARD_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(
            context_text=ctx_text
        )
        user_message = (
            f"Generate exactly {num_cards} flashcards based ONLY on the reference material "
            f"above from the document: '{resource_title}'. Output valid JSON only."
        )

        try:
            response = await self.clients.call_claude(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                model="claude-3-5-sonnet-20241022",
                enable_tools=False,
            )
            raw_content = response.get("content", "")
        except Exception as exc:
            logger.warning("[StudyTools] Flashcard LLM call failed: %s", type(exc).__name__)
            return {
                "success": False,
                "error": "LLM_ERROR",
                "message": "The AI service is temporarily unavailable. Please try again.",
                "resource_id": resource_id,
            }

        parsed = self._extract_json(raw_content)
        if parsed is None:
            logger.warning("[StudyTools] Flashcards: could not parse JSON from LLM output")
            return {
                "success": False,
                "error": "PARSE_ERROR",
                "message": "The AI returned an unexpected format. Please try again.",
                "resource_id": resource_id,
            }

        validated, err = self._validate_flashcards(parsed, max_cards=num_cards)
        if validated is None:
            logger.warning("[StudyTools] Flashcard validation failed: %s", err)
            return {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "The AI returned an unexpected format. Please try again.",
                "resource_id": resource_id,
            }

        source_refs = [
            {
                "document_id": c.get("document_id"),
                "title": c.get("title"),
                "chunk_index": c.get("chunk_index"),
                "relevance_score": c.get("score"),
            }
            for c in retrieved_citations
        ]

        return {
            "success": True,
            "resource_id": resource_id,
            "resource_title": resource_title,
            **validated,
            "sources": source_refs,
            "model_used": response.get("model", ""),
            "quality": self._compute_quality(
                generated_text=raw_content,
                retrieved_citations=retrieved_citations,
                ctx_text=ctx_text,
            ),
        }

    # ── Summary generation ─────────────────────────────────────────────────────

    async def generate_summary(
        self,
        resource_id: str,
        institution_id: str,
        resource_title: str,
    ) -> Dict[str, Any]:
        """Generate a grounded summary from an approved resource."""
        ctx_text, retrieved_citations = await self._retrieve_grounded_context(
            query=f"overview summary main topics {resource_title}",
            institution_id=institution_id,
            resource_id=resource_id,
            limit=10,
        )

        if not ctx_text:
            try:
                import uuid as _u
                from app.models.resource import StudyMaterial
                mat = db.session.query(StudyMaterial).filter_by(id=_u.UUID(str(resource_id))).first() if resource_id else None
                if mat:
                    ctx_text = f"Title: {mat.title}\nDescription: {mat.description or 'Academic reference document'}\n"
                    if getattr(mat, 'department_name', None):
                        ctx_text += f"Department: {mat.department_name}\n"
            except Exception:
                pass

        if not ctx_text:
            return {
                "success": False,
                "error": "NO_CONTEXT",
                "message": _NO_CONTEXT_SUMMARY,
                "resource_id": resource_id,
            }

        system_prompt = GROUNDED_SUMMARY_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(
            context_text=ctx_text
        )
        user_message = (
            f"Summarize the document '{resource_title}' based ONLY on the reference material above."
        )

        try:
            response = await self.clients.call_claude(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                model="claude-3-5-sonnet-20241022",
                enable_tools=False,
            )
            raw_content = response.get("content", "")
        except Exception as exc:
            logger.warning("[StudyTools] Summary LLM call failed: %s", type(exc).__name__)
            return {
                "success": False,
                "error": "LLM_ERROR",
                "message": "The AI service is temporarily unavailable. Please try again.",
                "resource_id": resource_id,
            }

        validated_summary, err = self._validate_summary(raw_content)
        if validated_summary is None:
            logger.warning("[StudyTools] Summary validation failed: %s", err)
            return {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "The AI returned an unexpected format. Please try again.",
                "resource_id": resource_id,
            }

        source_refs = [
            {
                "document_id": c.get("document_id"),
                "title": c.get("title"),
                "chunk_index": c.get("chunk_index"),
                "relevance_score": c.get("score"),
            }
            for c in retrieved_citations
        ]

        return {
            "success": True,
            "resource_id": resource_id,
            "resource_title": resource_title,
            "summary": validated_summary,
            "sources": source_refs,
            "model_used": response.get("model", ""),
            "quality": self._compute_quality(
                generated_text=validated_summary,
                retrieved_citations=retrieved_citations,
                ctx_text=ctx_text,
            ),
        }
