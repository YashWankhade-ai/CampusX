import json
from typing import Optional, Dict, Any
from .clients import AIClients
from .prompt_templates import QUIZ_GENERATOR_PROMPT

class QuizService:
    def __init__(self, ai_clients: Optional[AIClients] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()

    async def generate_quiz(self, topic: str, num_questions: int = 5, **kwargs) -> Dict[str, Any]:
        prompt = QUIZ_GENERATOR_PROMPT.format(num_questions=num_questions, topic=topic, text=topic)
        res = await self.clients.call_claude(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are an expert academic quiz generator.",
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
                "topic": topic,
                "questions": [
                    {
                        "question_number": 1,
                        "question": f"Sample quiz question about {topic}",
                        "options": ["Option A", "Option B", "Option C", "Option D"],
                        "correct_answer_index": 0,
                        "explanation": "Default explanation"
                    }
                ]
            }
