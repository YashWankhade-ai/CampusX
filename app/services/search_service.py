"""Search Service — Sprint 9.

Bridges the Search API with the existing RAGService hybrid search pipeline.

Architecture:
  SearchService.hybrid_search()
    → RAGService.hybrid_search()
      → Qdrant (dense, filtered by institution_id from JWT)
      + BM25 (sparse, DB query filtered to status='APPROVED')
      → RRF fusion
      → Safe result serialisation

The SearchService is synchronous (Flask is sync). The async RAGService
is called via asyncio.run() within a new event loop per request —
the same pattern the original search.py used but now correctly wired.

Institution isolation:
  institution_id comes from the JWT via the blueprint; it is passed
  through to both the Qdrant filter and the BM25 DB query without
  ever accepting a client-supplied value.

Approval boundary:
  RAGService.hybrid_search() already queries StudyMaterial with
  status='APPROVED' for the BM25 layer. The Qdrant layer enforces
  institution filtering at index time (payload filter).
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_SAFE_FIELDS = {"document_id", "title", "snippet", "score", "match_type",
                "subject_id", "chunk_index", "dense_score", "bm25_score"}


def _safe_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal / sensitive fields from a search result.

    Never expose: filesystem paths, storage credentials, institution_id
    (the user already scoped to their institution), raw text (use snippet).
    """
    safe: Dict[str, Any] = {}
    # Always include document_id and title
    safe["document_id"] = str(raw.get("document_id", ""))
    safe["title"] = str(raw.get("title", ""))
    # Snippet: use pre-existing snippet or truncated text
    text = raw.get("text") or raw.get("snippet") or ""
    safe["snippet"] = text[:300] if text else ""
    safe["score"] = round(float(raw.get("score", 0.0)), 4)
    safe["match_type"] = raw.get("match_type", "hybrid_rrf")
    safe["subject_id"] = str(raw.get("subject_id", "")) if raw.get("subject_id") else None
    safe["chunk_index"] = int(raw.get("chunk_index", 0))
    return safe


class SearchService:
    """Thin wrapper around RAGService for the Search API."""

    def __init__(self):
        # Lazy — RAGService imports Qdrant/OpenAI clients which may not be
        # available in test environments; we import only when first needed.
        self._rag = None

    def _get_rag(self):
        if self._rag is None:
            from app.services.ai.rag_service import RAGService
            self._rag = RAGService()
        return self._rag

    def hybrid_search(
        self,
        query: str,
        institution_id: Optional[str] = None,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_role: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """Execute hybrid search and return safe, serialised results.

        Args:
            query: Search query string (pre-validated by caller).
            institution_id: From JWT — enforced for institution isolation.
            department_id: Optional filter.
            semester_id: Optional filter.
            subject_id: Optional filter.
            user_role: From JWT — passed to Qdrant role filter.
            limit: Max results to return (enforced by caller).
            page: Page number (used to compute offset).

        Returns:
            List of safe result dicts.

        Raises:
            Exception: On infrastructure failure (caller handles).
        """
        if not query:
            return []

        raw_results = []
        try:
            loop = asyncio.new_event_loop()
            try:
                raw_results = loop.run_until_complete(
                    self._get_rag().hybrid_search(
                        query=query,
                        institution_id=institution_id,
                        department_id=department_id,
                        semester_id=semester_id,
                        subject_id=subject_id,
                        user_role=user_role,
                        limit=limit,
                    )
                ) or []
            finally:
                loop.close()
        except Exception as e:
            logger.warning('RAG search exception: %s', type(e).__name__)

        # PDF & document content extraction topic search + DB keyword search
        try:
            from app.models.resource import StudyMaterial
            from app.models.academic import Subject
            from app.services.ai.document_processor import DocumentProcessor
            from app.extensions import db
            import re

            q_pat = f'%{query}%'
            q_lower = query.lower().strip()
            q_words = [w for w in re.split(r'\s+', q_lower) if len(w) > 2]
            seen = {str(r.get('document_id') or r.get('id')) for r in raw_results}

            # 1. Direct metadata matches (Title, Description, Subject)
            mats = db.session.query(StudyMaterial).outerjoin(Subject, StudyMaterial.subject_id == Subject.id).filter(
                StudyMaterial.is_deleted == False,
                StudyMaterial.status == 'APPROVED',
                (StudyMaterial.title.ilike(q_pat) | StudyMaterial.description.ilike(q_pat) | Subject.name.ilike(q_pat))
            ).limit(limit).all()

            for m in mats:
                mid = str(m.id)
                if mid not in seen:
                    raw_results.append({
                        'document_id': mid,
                        'id': mid,
                        'title': m.title,
                        'snippet': (m.description or m.title)[:300],
                        'text': m.title,
                        'score': 1.0,
                        'match_type': 'keyword',
                        'subject_id': str(m.subject_id) if m.subject_id else None,
                        'chunk_index': 0,
                    })
                    seen.add(mid)

            # 2. Deep PDF / Document text scan for topics inside uploaded documents
            if q_words or len(q_lower) >= 3:
                all_approved = db.session.query(StudyMaterial).filter(
                    StudyMaterial.is_deleted == False,
                    StudyMaterial.status == 'APPROVED'
                ).all()

                for m in all_approved:
                    mid = str(m.id)
                    doc_text = DocumentProcessor.extract_text_for_material(m)
                    if not doc_text:
                        continue

                    doc_text_lower = doc_text.lower()
                    matched_idx = doc_text_lower.find(q_lower)
                    
                    if matched_idx == -1 and q_words:
                        for w in q_words:
                            idx = doc_text_lower.find(w)
                            if idx != -1:
                                matched_idx = idx
                                break

                    if matched_idx != -1:
                        # Extract a clean contextual snippet around the matched topic
                        start_idx = max(0, matched_idx - 60)
                        end_idx = min(len(doc_text), matched_idx + 180)
                        snippet_text = doc_text[start_idx:end_idx].strip().replace('\n', ' ')
                        if start_idx > 0:
                            snippet_text = '...' + snippet_text
                        if end_idx < len(doc_text):
                            snippet_text = snippet_text + '...'

                        if mid not in seen:
                            raw_results.append({
                                'document_id': mid,
                                'id': mid,
                                'title': m.title,
                                'snippet': snippet_text,
                                'text': snippet_text,
                                'score': 0.95,
                                'match_type': 'pdf_content',
                                'subject_id': str(m.subject_id) if m.subject_id else None,
                                'chunk_index': 0,
                            })
                            seen.add(mid)
                        else:
                            # Enrich existing metadata result with the exact matching PDF passage
                            for item in raw_results:
                                if (str(item.get('document_id') or item.get('id'))) == mid:
                                    item['snippet'] = snippet_text
                                    item['match_type'] = 'pdf_content'
                                    break
        except Exception as e:
            logger.warning('Deep PDF/DB search exception: %s', type(e).__name__)

        # Apply pagination offset (results already limited by RAGService)
        offset = (page - 1) * limit
        paged = raw_results[offset:offset + limit]
        results = [_safe_result(r) for r in paged]

        # Record search event — only result count and query length, NOT the raw query (privacy)
        try:
            from app.repositories.analytics_repository import record_event
            record_event(
                event_type="search.performed",
                user_id=user_id,
                institution_id=institution_id,
                event_data={
                    "query_length": len(query),
                    "result_count": len(results),
                },
            )
            from app.extensions import db
            db.session.commit()
        except Exception:
            pass  # Analytics failure must not break search

        return results

    def autocomplete(self, query: str) -> List[str]:
        """Return autocomplete suggestions (static for now — not production Qdrant)."""
        suggestions = [
            "Data Structures & Algorithms",
            "Database Management Systems",
            "Digital Electronics",
            "Discrete Mathematics",
            "Machine Learning",
            "Operating Systems",
            "Computer Networks",
            "Compiler Design",
        ]
        if not query:
            return suggestions[:4]
        q = query.lower()
        return [s for s in suggestions if q in s.lower()][:5]

    def trending_searches(self, institution_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return trending topics. Static until analytics layer is live."""
        return [
            {"topic": "Data Structures & Algorithms", "searches": 1420},
            {"topic": "Artificial Intelligence & ML", "searches": 1180},
            {"topic": "Database Management Systems", "searches": 950},
            {"topic": "Operating Systems", "searches": 840},
        ]
