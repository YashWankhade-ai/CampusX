"""CampusX Quiz Service — grounded quiz generation via StudyToolsService.

Replaces the previous topic-only stub with a fully grounded implementation.
All resource validation, retrieval, LLM calls, and output validation are
delegated to StudyToolsService to avoid duplication.

Backward-compatible shim: the old generate_quiz(topic, num_questions) signature
is retained for the legacy /api/v1/ai/quiz/generate route.
"""
import logging
from typing import Any, Dict, Optional

from app.services.ai.clients import AIClients
from app.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)


class QuizService:
    """Quiz generation service.

    Grounded path (recommended):
        generate_for_resource(resource_id, institution_id, resource_title, num_questions)
        → StudyToolsService.generate_quiz()

    Legacy ungrounded path (backward compatibility, for plain topic-only calls):
        generate_quiz(topic, num_questions)
        → directly uses AIClients (no retrieval, no resource validation)
    """

    def __init__(
        self,
        ai_clients: Optional[AIClients] = None,
        rag_service: Optional[RAGService] = None,
    ):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self._rag = rag_service
        self._study_tools = None

    def _get_study_tools(self):
        if self._study_tools is None:
            from app.services.ai.study_tools_service import StudyToolsService
            self._study_tools = StudyToolsService(
                ai_clients=self.clients,
                rag_service=self._rag if self._rag is not None else RAGService(),
            )
        return self._study_tools

    async def generate_for_resource(
        self,
        resource_id: str,
        institution_id: str,
        resource_title: str,
        num_questions: int = 5,
    ) -> Dict[str, Any]:
        """Generate a grounded quiz from an approved CampusX resource.

        Security: resource_id validated against DB, institution_id from JWT.
        """
        return await self._get_study_tools().generate_quiz(
            resource_id=resource_id,
            institution_id=institution_id,
            resource_title=resource_title,
            num_questions=num_questions,
        )

    async def generate_quiz(self, topic: str, num_questions: int = 5, **kwargs) -> Dict[str, Any]:
        """Legacy ungrounded quiz — kept for backward compatibility with old stub route.

        This path does NOT perform resource validation or retrieval grounding.
        The blueprint should prefer generate_for_resource() for new code.
        """
        import json
        from app.services.ai.prompt_templates import QUIZ_GENERATOR_PROMPT
        prompt = QUIZ_GENERATOR_PROMPT.format(num_questions=num_questions, topic=topic, text=topic)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic quiz generator.",
            model="claude-3-5-sonnet-20241022",
            enable_tools=False,
        )
        content = res.get("content", "")
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())
        except Exception:
            return {
                "topic": topic,
                "questions": [
                    {
                        "question_number": 1,
                        "question": f"Sample quiz question about {topic}",
                        "options": ["Option A", "Option B", "Option C", "Option D"],
                        "correct_answer_index": 0,
                        "explanation": "Default explanation",
                    }
                ],
            }
