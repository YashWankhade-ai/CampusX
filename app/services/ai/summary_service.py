"""CampusX Summary Service — grounded summary generation via StudyToolsService.

Replaces the previous text-only stub with a fully grounded implementation.
"""
import logging
from typing import Any, Dict, Optional

from app.services.ai.clients import AIClients
from app.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)


class SummaryService:
    """Summary generation service.

    Grounded path (recommended):
        generate_for_resource(resource_id, institution_id, resource_title)
        → StudyToolsService.generate_summary()

    Legacy ungrounded path (backward compatibility):
        summarize(text) / summarize_topic(topic, ...)
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
    ) -> Dict[str, Any]:
        """Generate a grounded summary from an approved CampusX resource."""
        return await self._get_study_tools().generate_summary(
            resource_id=resource_id,
            institution_id=institution_id,
            resource_title=resource_title,
        )

    async def summarize(self, text: str) -> str:
        """Legacy ungrounded summarize — kept for backward compatibility."""
        from app.services.ai.prompt_templates import SUMMARY_PROMPT
        prompt = SUMMARY_PROMPT.format(text=text)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic summarizer.",
            model="claude-3-5-sonnet-20241022",
            enable_tools=False,
        )
        return res.get("content", "")

    async def summarize_topic(self, topic: str, institution: str = "", subject: str = "") -> str:
        """Legacy topic summarizer — kept for backward compatibility."""
        return await self.summarize(f"Topic: {topic}")
