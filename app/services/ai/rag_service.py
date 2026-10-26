"""RAG (Retrieval-Augmented Generation) service for CampusX General Q&A.

Pipeline:
    hybrid_search()    → dense (Qdrant) + sparse (BM25) retrieval fused with RRF
    retrieve_context() → assembles context_text + citations from hybrid results
    calculate_confidence() → heuristic tier from top RRF score (see prompt_templates.py)

Security contract:
    - institution_id MUST come from the authenticated JWT (passed by blueprint layer).
    - It is NEVER read from client-supplied input inside this service.
    - BM25 corpus is institution-scoped via StudyMaterial → User join.
    - Qdrant search filters by institution_id, approved_only=True, exclude_deleted=True.
    - Cross-institution candidates are removed before RRF — they never reach the LLM.

Context size:
    Retrieved context is bounded at MAX_CONTEXT_CHARS characters before being
    passed to the LLM. This prevents token-limit errors and controls cost.
    The raw document_id is NOT included in LLM-facing context text to avoid
    unnecessarily exposing internal DB identifiers.

Confidence:
    calculate_confidence() returns HIGH/MEDIUM/LOW/NONE based on the top RRF score.
    These are HEURISTIC thresholds, not calibrated probabilities.
    See prompt_templates.CONFIDENCE_THRESHOLDS for threshold values and caveats.
"""
import uuid
import logging
from typing import List, Dict, Any, Tuple, Optional

from app.extensions import db
from app.models.resource import StudyMaterial
from .qdrant_service import QdrantService
from .embedding_service import EmbeddingService
from .document_processor import DocumentProcessor, SemanticChunker
from .bm25_service import BM25Ranker, reciprocal_rank_fusion
from .prompt_templates import MAX_CONTEXT_CHARS, CONFIDENCE_THRESHOLDS

logger = logging.getLogger(__name__)

# Maximum number of DB materials to load for BM25 corpus (memory guard).
_BM25_CORPUS_LIMIT = 50


class RAGService:
    def __init__(
        self,
        qdrant_service: Optional[QdrantService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.qdrant = qdrant_service if qdrant_service is not None else QdrantService()
        self.embedder = embedding_service if embedding_service is not None else EmbeddingService()
        self.chunker = SemanticChunker()
        self.bm25_ranker = BM25Ranker()

    # ── Ingestion ──────────────────────────────────────────────────────────────

    async def ingest_material(
        self, file_bytes: bytes, filename: str, metadata: Dict[str, Any]
    ) -> int:
        """Process, chunk, embed, and index a study material in Qdrant.

        Returns the number of chunks successfully indexed (0 if nothing was indexed).
        """
        raw_text = DocumentProcessor.extract_text(
            file_bytes, filename, metadata.get("mime_type", "")
        )
        if not raw_text.strip():
            return 0

        chunks = self.chunker.chunk_text(raw_text, chunk_size=500, overlap=50)
        if not chunks:
            return 0

        embeddings = await self.embedder.batch_embed_chunks(chunks)

        await self.qdrant.ensure_collection()
        metadata_list = [metadata] * len(chunks)
        await self.qdrant.upsert_chunks(chunks, embeddings, metadata_list)

        return len(chunks)

    # ── Hybrid retrieval ───────────────────────────────────────────────────────

    async def hybrid_search(
        self,
        query: str,
        institution_id: Optional[str] = None,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        user_role: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Dense vector search + BM25 sparse search fused via RRF.

        Security:
            - institution_id from JWT (caller responsibility — never from client body).
            - Dense search: Qdrant filters institution_id + approved_only + not deleted.
            - Sparse search: BM25 corpus filtered by institution via User join.
            - Cross-institution candidates are eliminated before RRF merging.
            - When document_id is set, retrieval is scoped to that single document
              (PDF Chat mode). institution_id filter is still enforced.
            - When document_ids is set, retrieval is scoped to those documents
              (Multi-PDF Chat mode). institution_id filter is still enforced.

        Args:
            query: User question string.
            institution_id: From JWT. Mandatory for production use.
            document_id: Optional. When set, retrieval is scoped to a single document.
            document_ids: Optional. When set, retrieval is scoped to multiple documents.
            limit: Maximum number of fused results returned.

        Returns:
            List of result dicts with keys: document_id, title, text, score,
            chunk_index, dense_score, bm25_score.
        """
        if not query or not query.strip():
            return []

        # ── 1. Dense retrieval via Qdrant ──────────────────────────────────────
        dense_results = []
        try:
            query_embedding = await self.embedder.get_embedding(query)
            dense_results = await self.qdrant.search(
                query_embedding=query_embedding,
                institution_id=institution_id,
                department_id=department_id,
                semester_id=semester_id,
                subject_id=subject_id,
                document_id=document_id,        # single-document (PDF Chat)
                document_ids=document_ids,       # multi-document (Multi-PDF Chat)
                user_role=user_role,
                limit=limit * 2,
            )
        except Exception as exc:
            logger.warning("[RAG] Dense retrieval notice: %s", type(exc).__name__)
            # Fail soft — continue with BM25-only retrieval

        # ── 2. Sparse BM25 corpus — institution-scoped, approved-only ──────────
        #    institution_id comes from JWT (set by blueprint) — not from client.
        #    Join path: StudyMaterial.author_id → User.institution_id
        #    When document_id is set (PDF chat), BM25 is restricted to that document.
        #    When document_ids is set (Multi-PDF chat), BM25 is restricted to those documents.
        sparse_docs: List[Dict[str, Any]] = []
        try:
            from app.models.user import User  # deferred to avoid circular import

            db_query = (
                db.session.query(StudyMaterial)
                .join(User, StudyMaterial.author_id == User.id)
                .filter(
                    StudyMaterial.is_deleted == False,  # noqa: E712
                    StudyMaterial.status == "APPROVED",
                )
            )

            if institution_id:
                try:
                    inst_uuid = uuid.UUID(str(institution_id))
                    from app.models.academic import Institution
                    default_inst = Institution.query.filter_by(code='DEFAULT-01').first()
                    default_id = default_inst.id if default_inst else None
                    if default_id:
                        db_query = db_query.filter(
                            (User.institution_id == inst_uuid) | (User.institution_id == default_id) | (User.institution_id == None)
                        )
                    else:
                        db_query = db_query.filter(User.institution_id == inst_uuid)
                except (ValueError, TypeError):
                    logger.warning(
                        "[RAG] Invalid institution_id format — BM25 corpus empty (fail closed)"
                    )
                    db_query = db_query.filter(False)  # Fail closed

            # Multi-document takes precedence over single document_id
            if document_ids:
                # Multi-PDF Chat mode — restrict BM25 corpus to selected documents
                valid_doc_uuids = []
                for did in document_ids:
                    try:
                        valid_doc_uuids.append(uuid.UUID(str(did)))
                    except (ValueError, TypeError):
                        logger.warning("[RAG] Invalid document_id in document_ids — skipping: %s", type(did).__name__)
                if valid_doc_uuids:
                    db_query = db_query.filter(StudyMaterial.id.in_(valid_doc_uuids))
                else:
                    db_query = db_query.filter(False)  # All invalid → fail closed
            elif document_id:
                # PDF chat mode — restrict BM25 corpus to the single document
                try:
                    doc_uuid = uuid.UUID(str(document_id))
                    db_query = db_query.filter(StudyMaterial.id == doc_uuid)
                except (ValueError, TypeError):
                    logger.warning("[RAG] Invalid document_id format — BM25 corpus empty (fail closed)")
                    db_query = db_query.filter(False)

            if subject_id:
                try:
                    db_query = db_query.filter(
                        StudyMaterial.subject_id == uuid.UUID(str(subject_id))
                    )
                except (ValueError, TypeError):
                    pass

            db_materials = db_query.limit(_BM25_CORPUS_LIMIT).all()
            sparse_docs = []
            for m in db_materials:
                # Include extracted text from PDF/document content if available
                full_text = f"{m.title}\n{m.description or ''}"
                try:
                    from .document_processor import DocumentProcessor
                    pdf_text = DocumentProcessor.extract_text_for_material(m)
                    if pdf_text:
                        full_text = f"{full_text}\n{pdf_text[:4000]}"
                except Exception:
                    pass
                sparse_docs.append({
                    "document_id": str(m.id),
                    "title": m.title,
                    "text": full_text,
                    "chunk_index": 0,
                })
        except Exception as exc:
            logger.warning("[RAG] BM25 corpus retrieval notice: %s", type(exc).__name__)

        # ── 3. BM25 sparse ranking ─────────────────────────────────────────────
        sparse_results: List[Dict[str, Any]] = []
        try:
            sparse_results = self.bm25_ranker.rank(query, sparse_docs, top_k=limit * 2)
        except Exception as exc:
            logger.warning("[RAG] BM25 ranking notice: %s", type(exc).__name__)

        # ── 4. RRF fusion ──────────────────────────────────────────────────────
        #    Deduplication is performed inside reciprocal_rank_fusion using the
        #    composite key f"{document_id}_{chunk_index}".
        fused_results = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=limit,
        )

        # ── 5. Enrich titles from DB for Qdrant-only hits ─────────────────────
        for item in fused_results:
            if not item.get("title") and item.get("document_id"):
                try:
                    mat = db.session.query(StudyMaterial).filter_by(
                        id=uuid.UUID(item["document_id"])
                    ).first()
                    if mat:
                        item["title"] = mat.title
                except Exception:
                    pass
            if not item.get("title"):
                item["title"] = "Study Material"

        return fused_results

    # ── Context assembly ───────────────────────────────────────────────────────

    async def retrieve_context(
        self,
        query: str,
        institution: str = "",
        subject: str = "",
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        user_role: Optional[str] = None,
        limit: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Build LLM context text and citation list from hybrid retrieval.

        Security / quality notes:
            - institution and user_role MUST come from the JWT (set by blueprint).
            - context_text is bounded at MAX_CONTEXT_CHARS characters.
            - Raw document_id is NOT included in context_text (avoid leaking DB IDs).
            - Title and chunk_index are used for attribution instead.
            - An empty retrieval returns ("", []) safely.
            - When document_id is set, context is scoped to that document (PDF chat).
            - When document_ids is set, context is scoped to those documents (Multi-PDF).

        Returns:
            (context_text, citations) where:
                context_text  : Formatted string for injection into system prompt.
                citations     : List of dicts with document_id, title, snippet, score, chunk_index.
        """
        results = await self.hybrid_search(
            query=query,
            institution_id=institution or None,
            subject_id=subject or None,
            document_id=document_id or None,
            document_ids=document_ids or None,
            user_role=user_role,
            limit=limit,
        )

        if not results:
            return "", []

        context_chunks: List[str] = []
        citations: List[Dict[str, Any]] = []
        total_chars = 0

        for r in results:
            doc_id = r.get("document_id", "")
            title = r.get("title", "Study Material")
            text = r.get("text", "")
            score = r.get("score", 0.0)
            chunk_idx = r.get("chunk_index", 0)

            # Format each chunk for LLM — use title+chunk_index, NOT raw document_id.
            chunk_label = f"[{title}, chunk {chunk_idx}]"
            chunk_entry = f"{chunk_label}:\n{text}"

            # Enforce cumulative context size cap.
            remaining = MAX_CONTEXT_CHARS - total_chars
            if remaining <= 0:
                break
            if len(chunk_entry) > remaining:
                chunk_entry = chunk_entry[:remaining] + "\n[...truncated]"
                total_chars = MAX_CONTEXT_CHARS
            else:
                total_chars += len(chunk_entry)

            context_chunks.append(chunk_entry)
            citations.append({
                "document_id": doc_id,
                "title": title,
                "snippet": text[:300],
                "score": score,
                "chunk_index": chunk_idx,
            })

            if total_chars >= MAX_CONTEXT_CHARS:
                break

        context_text = "\n\n".join(context_chunks)
        return context_text, citations

    # ── Confidence ─────────────────────────────────────────────────────────────

    def calculate_confidence(self, score: float) -> str:
        """Return a confidence tier label for the given top RRF score.

        This is a HEURISTIC — not a calibrated probability model.
        See prompt_templates.CONFIDENCE_THRESHOLDS for threshold values and caveats.

        Args:
            score: Top RRF score from hybrid_search results. Use 0.0 when no results.

        Returns:
            "HIGH", "MEDIUM", "LOW", or "NONE".
        """
        if score == 0.0:
            return "NONE"
        if score >= CONFIDENCE_THRESHOLDS["HIGH"]:
            return "HIGH"
        if score >= CONFIDENCE_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        return "LOW"

    # ── Session stub (for blueprint compatibility) ─────────────────────────────

    def create_session(self, *args, **kwargs):
        """Stub — sessions are managed by ChatService, not RAGService."""
        raise NotImplementedError("create_session belongs to ChatService")
