import uuid
import logging
from typing import List, Dict, Any, Tuple, Optional
from app.extensions import db
from app.models.resource import StudyMaterial
from .qdrant_service import QdrantService
from .embedding_service import EmbeddingService
from .document_processor import DocumentProcessor, SemanticChunker
from .bm25_service import BM25Ranker, reciprocal_rank_fusion

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self, qdrant_service: Optional[QdrantService] = None, embedding_service: Optional[EmbeddingService] = None):
        self.qdrant = qdrant_service if qdrant_service is not None else QdrantService()
        self.embedder = embedding_service if embedding_service is not None else EmbeddingService()
        self.chunker = SemanticChunker()
        self.bm25_ranker = BM25Ranker()

    async def ingest_material(self, file_bytes: bytes, filename: str, metadata: Dict[str, Any]) -> int:
        """
        Process, chunk, embed, and index study material in Qdrant & database.
        """
        # 1. Multi-format Text Extraction (PDF, Docx, PPTX, Image OCR)
        raw_text = DocumentProcessor.extract_text(file_bytes, filename, metadata.get("mime_type", ""))
        if not raw_text.strip():
            return 0

        # 2. Semantic Overlapping Chunking
        chunks = self.chunker.chunk_text(raw_text, chunk_size=500, overlap=50)
        if not chunks:
            return 0

        # 3. Generate Dense Embeddings
        embeddings = await self.embedder.batch_embed_chunks(chunks)

        # 4. Upsert to Qdrant Vector Collection
        await self.qdrant.ensure_collection()
        metadata_list = [metadata] * len(chunks)
        await self.qdrant.upsert_chunks(chunks, embeddings, metadata_list)

        return len(chunks)

    async def hybrid_search(
        self,
        query: str,
        institution_id: Optional[str] = None,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_role: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Executes Dense Vector Search + BM25 Sparse Search and fuses results via Reciprocal Rank Fusion (RRF).
        Enforces metadata & RBAC security permission filtering.
        """
        # 1. Dense Vector Search via Qdrant
        query_embedding = await self.embedder.get_embedding(query)
        dense_results = await self.qdrant.search(
            query_embedding=query_embedding,
            institution_id=institution_id,
            department_id=department_id,
            semester_id=semester_id,
            subject_id=subject_id,
            user_role=user_role,
            limit=limit * 2
        )

        # 2. Query Local Database Materials for BM25 Sparse Ranking
        sparse_docs = []
        try:
            db_query = db.session.query(StudyMaterial).filter(StudyMaterial.is_deleted == False, StudyMaterial.status == "APPROVED")
            if subject_id:
                try:
                    db_query = db_query.filter(StudyMaterial.subject_id == uuid.UUID(str(subject_id)))
                except Exception:
                    pass

            db_materials = db_query.limit(50).all()
            sparse_docs = [
                {
                    "document_id": str(m.id),
                    "title": m.title,
                    "text": f"{m.title}\n{m.description or ''}",
                    "chunk_index": 0
                }
                for m in db_materials
            ]
        except Exception as e:
            logger.warning(f"Sparse DB retrieval notice: {e}")

        # 3. BM25 Sparse Ranking
        sparse_results = self.bm25_ranker.rank(query, sparse_docs, top_k=limit * 2)

        # 4. Reciprocal Rank Fusion (RRF)
        fused_results = reciprocal_rank_fusion(dense_results=dense_results, sparse_results=sparse_results, top_k=limit)

        # Ensure document metadata titles
        for item in fused_results:
            if not item.get("title") and item.get("document_id"):
                try:
                    mat = db.session.query(StudyMaterial).filter_by(id=uuid.UUID(item["document_id"])).first()
                    if mat:
                        item["title"] = mat.title
                except Exception:
                    pass
            if not item.get("title"):
                item["title"] = "Study Material"

        return fused_results

    async def retrieve_context(
        self,
        query: str,
        institution: str = "",
        subject: str = "",
        user_role: Optional[str] = None,
        limit: int = 5
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Returns (context_text, source_citations) using hybrid search.
        """
        results = await self.hybrid_search(query=query, subject_id=subject, user_role=user_role, limit=limit)
        if not results:
            return "", []

        context_chunks = []
        citations = []
        for r in results:
            doc_id = r.get("document_id", "")
            title = r.get("title", "Study Material")
            text = r.get("text", "")
            score = r.get("score", 0.0)

            context_chunks.append(f"Document [{title}] (ID: {doc_id}):\n{text}")
            citations.append({
                "document_id": doc_id,
                "title": title,
                "snippet": text[:300],
                "score": score,
                "chunk_index": r.get("chunk_index", 0)
            })

        context_text = "\n\n".join(context_chunks)
        return context_text, citations

    def calculate_confidence(self, score: float) -> str:
        if score >= 0.03:
            return "HIGH"
        elif score >= 0.015:
            return "MEDIUM"
        else:
            return "LOW"
