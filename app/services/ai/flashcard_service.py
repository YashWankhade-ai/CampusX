"""CampusX Flashcard Service — grounded flashcard generation via StudyToolsService.

Replaces the previous text-only stub with a fully grounded implementation.
"""
import logging
from typing import Any, Dict, Optional

from app.services.ai.clients import AIClients
from app.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)


class FlashcardService:
    """Flashcard generation service.

    Grounded path (recommended):
        generate_for_resource(resource_id, institution_id, resource_title, num_cards)
        → StudyToolsService.generate_flashcards()

    Legacy ungrounded path (backward compatibility):
        generate_flashcards(text, num_cards)
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
        num_cards: int = 10,
    ) -> Dict[str, Any]:
        """Generate grounded flashcards from an approved CampusX resource."""
        return await self._get_study_tools().generate_flashcards(
            resource_id=resource_id,
            institution_id=institution_id,
            resource_title=resource_title,
            num_cards=num_cards,
        )

    async def generate_flashcards(self, text: str, num_cards: int = 5, **kwargs) -> Dict[str, Any]:
        """Legacy ungrounded flashcards — kept for backward compatibility."""
        import json
        from app.services.ai.prompt_templates import FLASHCARD_GENERATOR_PROMPT
        prompt = FLASHCARD_GENERATOR_PROMPT.format(num_cards=num_cards, text=text)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic flashcard generator.",
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
                "flashcards": [
                    {
                        "front": f"Key concept in {text[:30]}",
                        "back": "Detailed definition and study explanation.",
                        "category": "General",
                    }
                ]
            }
