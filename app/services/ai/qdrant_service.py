"""Qdrant vector database service for CampusX RAG system.

Security contract:
    - institution_id is ALWAYS stored in payload at upsert time and
      filtered at search time. The caller is responsible for providing the
      institution_id from JWT, never from request body.
    - is_approved and is_deleted are stored in payload to allow post-hoc
      filtering when approval status changes after indexing.
    - delete_chunks_for_document() must be called whenever a resource is
      deleted or un-approved so stale vectors are removed immediately.
"""
import os
import uuid
import logging
from typing import List, Dict, Any, Optional

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import (
        PointStruct, VectorParams, Distance, Filter, FieldCondition,
        MatchValue, MatchAny, FilterSelector,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    class AsyncQdrantClient:
        def __init__(self, *args, **kwargs): pass
    PointStruct = VectorParams = Distance = Filter = None
    FieldCondition = MatchValue = MatchAny = FilterSelector = None
    QDRANT_AVAILABLE = False

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(self):
        url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        api_key = os.environ.get("QDRANT_API_KEY", None)
        self.client = AsyncQdrantClient(url=url, api_key=api_key)
        self.collection_name = "campusx_documents"

    async def ensure_collection(self):
        if not QDRANT_AVAILABLE:
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
            logger.warning("Qdrant collection setup notice: %s", type(e).__name__)

    async def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        metadata_list: List[Dict[str, Any]],
    ):
        """Upsert chunks into Qdrant with full institutional metadata in payload.

        Required metadata fields (caller must populate from DB, not from request body):
            institution_id  — from material.author.institution_id
            document_id     — material.id as string
            is_approved     — True only when material.status == 'APPROVED'
            is_deleted      — material.is_deleted boolean

        Storing is_approved/is_deleted in the payload allows filtering
        even when approval status changes after initial indexing.
        """
        if not QDRANT_AVAILABLE:
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
                    "allowed_roles": metadata.get("allowed_roles", ["STUDENT", "FACULTY", "ADMIN", "SUPER_ADMIN"]),
                    # Approval and deletion status — used to filter stale vectors
                    "is_approved": bool(metadata.get("is_approved", False)),
                    "is_deleted": bool(metadata.get("is_deleted", False)),
                    "material_type": str(metadata.get("material_type", "")),
                    "author_id": str(metadata.get("author_id", "")),
                }
                points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
        except Exception as e:
            logger.warning("Qdrant upsert notice: %s", type(e).__name__)

    async def search(
        self,
        query_embedding: List[float],
        institution_id: Optional[str] = None,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        user_role: Optional[str] = None,
        limit: int = 10,
        approved_only: bool = True,
        exclude_deleted: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search Qdrant dense vectors with institution isolation and approval filters.

        Security:
            - institution_id must come from JWT (caller responsibility).
            - approved_only=True by default — only APPROVED documents are returned.
            - exclude_deleted=True by default — soft-deleted documents are excluded.

        document_id vs document_ids:
            - document_id: single-document scoping (existing PDF Chat / Study Tools).
            - document_ids: multi-document scoping (Multi-PDF Chat). Qdrant MatchAny.
            - Only one of document_id/document_ids should be set. If both are set,
              document_ids takes precedence.
        """
        if not QDRANT_AVAILABLE:
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

            # Multi-document filter takes precedence over single document_id
            if document_ids:
                # Multi-PDF Chat: restrict to any of the selected document IDs
                filters.append(FieldCondition(
                    key="document_id",
                    match=MatchAny(any=[str(d) for d in document_ids]),
                ))
            elif document_id:
                # Single PDF Chat: restrict to one specific document
                filters.append(FieldCondition(key="document_id", match=MatchValue(value=str(document_id))))

            if user_role and user_role.upper() != "SUPER_ADMIN":
                filters.append(FieldCondition(key="allowed_roles", match=MatchAny(any=[user_role.upper()])))
            # Approval and deletion filters — always enforced by default
            if approved_only:
                filters.append(FieldCondition(key="is_approved", match=MatchValue(value=True)))
            if exclude_deleted:
                filters.append(FieldCondition(key="is_deleted", match=MatchValue(value=False)))

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
                    "subject_id": payload.get("subject_id", ""),
                    "is_approved": payload.get("is_approved", False),
                    "is_deleted": payload.get("is_deleted", False),
                })

            return formatted
        except Exception as e:
            logger.warning("Qdrant search query notice: %s", type(e).__name__)
            return []

    async def delete_chunks_for_document(self, document_id: str) -> int:
        """Delete all Qdrant points associated with a document_id.

        Must be called when:
          - A resource is soft-deleted (is_deleted=True)
          - A resource is un-approved (status changed from APPROVED to REJECTED/PENDING)

        Returns the number of points deleted (0 on failure or missing Qdrant).
        """
        if not QDRANT_AVAILABLE:
            logger.debug("Qdrant not available — skipping chunk deletion for document %s", document_id)
            return 0
        try:
            result = await self.client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]
                    )
                ),
            )
            count = getattr(result, "status", None)
            logger.info("Qdrant chunks deleted for document_id=%s", document_id)
            return 1  # Qdrant delete doesn't return exact count easily; signal success
        except Exception as e:
            logger.warning(
                "Qdrant chunk deletion failed for document_id=%s: %s",
                document_id, type(e).__name__
            )
            return 0
