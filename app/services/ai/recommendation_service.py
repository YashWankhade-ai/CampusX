from typing import Optional, List, Dict, Any
from .clients import AIClients
from .rag_service import RAGService
import json

class RecommendationService:
    def __init__(self, ai_clients: Optional[AIClients] = None, rag_service: Optional[RAGService] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.rag = rag_service if rag_service is not None else RAGService()

    async def recommend_study_topics(self, past_performance: Dict[str, float], institution: str, subject: str) -> Dict[str, Any]:
        """
        past_performance maps topic names to scores (0.0 to 1.0)
        """
        # Identify weak areas
        weak_topics = [topic for topic, score in past_performance.items() if score < 0.7]
        
        if not weak_topics:
            return {"recommendations": [], "message": "Great job! You don't have any weak areas."}
            
        topics_str = ", ".join(weak_topics)
        
        system_prompt = (
            f"You are an academic advisor. The student is struggling with the following topics: {topics_str}. "
            f"Based on the subject '{subject}' at '{institution}', suggest 3 specific follow-up topics or concepts "
            f"they should study to improve their understanding of these weak areas. "
            f"Output in JSON format with a 'recommendations' array containing objects with "
            f"'topic', 'reason', and 'suggested_action'."
        )
        
        model = "gpt-4o-mini"
        
        response = await self.clients.call_openai(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Provide study recommendations in JSON."}
            ],
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        
        try:
            if result_text.startswith("```json"):
                result_text = result_text[7:-3]
            return json.loads(result_text)
        except json.JSONDecodeError:
            return {"error": "Failed to parse recommendations"}
