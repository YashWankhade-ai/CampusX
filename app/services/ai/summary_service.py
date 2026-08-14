from typing import Optional
from .clients import AIClients
from .prompt_templates import SUMMARY_PROMPT

class SummaryService:
    def __init__(self, ai_clients: Optional[AIClients] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()

    async def summarize(self, text: str) -> str:
        prompt = SUMMARY_PROMPT.format(text=text)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic summarizer.",
            model="claude-3-5-sonnet-20241022"
        )
        return res.get("content", "")

    async def summarize_topic(self, topic: str, institution: str = "", subject: str = "") -> str:
        return await self.summarize(f"Topic: {topic}")
