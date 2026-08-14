import json
from typing import Optional, Dict, Any
from .clients import AIClients
from .prompt_templates import FLASHCARD_GENERATOR_PROMPT

class FlashcardService:
    def __init__(self, ai_clients: Optional[AIClients] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()

    async def generate_flashcards(self, text: str, num_cards: int = 5, **kwargs) -> Dict[str, Any]:
        prompt = FLASHCARD_GENERATOR_PROMPT.format(num_cards=num_cards, text=text)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic flashcard generator.",
            model="claude-3-5-sonnet-20241022"
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
                        "category": "General"
                    }
                ]
            }
