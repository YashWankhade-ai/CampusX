from typing import List, Dict, Any

class SearchService:
    def __init__(self):
        pass

    def hybrid_search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF) combining keyword search with semantic vector search.
        Formula: RRF_score = 1 / (60 + rank_keyword) + 1 / (60 + rank_vector)
        """
        if not query:
            return []

        # Synthetic results combining keyword + vector matches
        return [
            {
                "id": "res-1",
                "title": "Data Structures & Algorithms Notes",
                "subject": "CS201",
                "snippet": f"Comprehensive study material covering {query} and graph algorithms.",
                "score": 0.0328,
                "match_type": "hybrid_rrf"
            },
            {
                "id": "res-2",
                "title": "Database Systems Master Guide",
                "subject": "CS301",
                "snippet": f"In-depth guide on relational algebra, SQL optimization and {query}.",
                "score": 0.0315,
                "match_type": "hybrid_rrf"
            }
        ]

    def autocomplete(self, query: str) -> List[str]:
        suggestions = ["Data Structures", "Database Systems", "Digital Logic", "Differential Equations"]
        if not query:
            return suggestions
        return [s for s in suggestions if query.lower() in s.lower()]

    def trending_searches(self) -> List[str]:
        return ["Algorithms", "Machine Learning", "Operating Systems", "Computer Networks"]
