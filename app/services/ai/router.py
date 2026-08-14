from typing import Dict, Any, List

class ModelRouter:
    """
    Routes queries to the appropriate model based on complexity.
    - Simple/MCQ queries -> gpt-4o-mini
    - Complex/Long-context synthesis -> claude-sonnet-4-6
    """
    
    @staticmethod
    def route_query(query: str, context_length: int) -> str:
        # Simple heuristics for routing
        simple_keywords = ["what is", "define", "mcq", "multiple choice", "true or false", "summarize briefly"]
        
        query_lower = query.lower()
        is_simple = any(keyword in query_lower for keyword in simple_keywords)
        
        # If the context is very long, prefer Claude for better long-context synthesis
        if context_length > 4000:
            return "claude-3-5-sonnet-20241022" # Using standard sonnet identifier
            
        if is_simple and len(query.split()) < 20:
            return "gpt-4o-mini"
            
        return "claude-3-5-sonnet-20241022"
