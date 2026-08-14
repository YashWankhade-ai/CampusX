import os
import uuid
import logging
from typing import List, Dict, Any, Optional

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance, Filter, FieldCondition, MatchValue, MatchAny
except ImportError:
    class AsyncQdrantClient:
        def __init__(self, *args, **kwargs): pass
    PointStruct = VectorParams = Distance = Filter = FieldCondition = MatchValue = MatchAny = None

logger = logging.getLogger(__name__)

class QdrantService:
    def __init__(self):
        url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        api_key = os.environ.get("QDRANT_API_KEY", None)
        self.client = AsyncQdrantClient(url=url, api_key=api_key)
        self.collection_name = "campusx_documents"

    async def ensure_collection(self):
        if not VectorParams:
            return
        try:
            collections = await self.client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)
            if not exists:
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=3072, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.warning(f"Qdrant collection setup notice: {e}")

    async def upsert_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]], metadata_list: List[Dict[str, Any]]):
        if not PointStruct:
            return
        try:
            points = []
            for i, (chunk, embedding, metadata) in enumerate(zip(chunks, embeddings, metadata_list)):
                point_id = str(uuid.uuid4())
                payload = {
                    "text": chunk.get("text", ""),
                    "institution_id": str(metadata.get("institution_id", "")),
                    "department_id": str(metadata.get("department_id", "")),
                    "semester_id": str(metadata.get("semester_id", "")),
                    "subject_id": str(metadata.get("subject_id", "")),
                    "document_id": str(metadata.get("document_id", "")),
                    "title": metadata.get("title", "Study Material"),
                    "chunk_index": chunk.get("chunk_index", i),
                    "allowed_roles": metadata.get("allowed_roles", ["STUDENT", "FACULTY", "ADMIN", "SUPER_ADMIN"])
                }
                points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
        except Exception as e:
            logger.warning(f"Qdrant upsert notice: {e}")

    async def search(
        self,
        query_embedding: List[float],
        institution_id: Optional[str] = None,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_role: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search Qdrant dense vectors with metadata & role permission filters.
        """
        if not FieldCondition:
            return []

        try:
            filters = []
            if institution_id:
                filters.append(FieldCondition(key="institution_id", match=MatchValue(value=str(institution_id))))
            if department_id:
                filters.append(FieldCondition(key="department_id", match=MatchValue(value=str(department_id))))
            if semester_id:
                filters.append(FieldCondition(key="semester_id", match=MatchValue(value=str(semester_id))))
            if subject_id:
                filters.append(FieldCondition(key="subject_id", match=MatchValue(value=str(subject_id))))
            if user_role and user_role.upper() != "SUPER_ADMIN":
                filters.append(FieldCondition(key="allowed_roles", match=MatchAny(any=[user_role.upper()])))

            qdrant_filter = Filter(must=filters) if filters else None

            results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=qdrant_filter,
                limit=limit,
                with_payload=True
            )

            formatted = []
            for r in results:
                payload = r.payload or {}
                formatted.append({
                    "id": str(r.id),
                    "score": round(r.score, 4),
                    "text": payload.get("text", ""),
                    "document_id": payload.get("document_id", ""),
                    "title": payload.get("title", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "institution_id": payload.get("institution_id", ""),
                    "subject_id": payload.get("subject_id", "")
                })

            return formatted
        except Exception as e:
            logger.warning(f"Qdrant search query notice: {e}")
            return []
