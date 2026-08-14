import os
import uuid
import asyncio
import logging
from app import create_app
from app.extensions import db
from app.models.resource import StudyMaterial, MaterialVersion
from app.services.ai.rag_service import RAGService
from .celery_app import celery

logger = logging.getLogger(__name__)

@celery.task(name="tasks.index_document")
def index_document_task(material_id: str, file_path: str, metadata: dict):
    """
    Celery background task for asynchronous document ingestion, multi-format text extraction,
    semantic chunking, dense embedding, and vector upserting.
    """
    app = create_app("development")
    with app.app_context():
        try:
            logger.info(f"[Celery Indexing Task] Starting ingestion for material_id={material_id}")
            mat_uuid = uuid.UUID(str(material_id))
            material = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()

            if not material:
                logger.error(f"[Celery Indexing Task] Material {material_id} not found in database.")
                return {"status": "FAILED", "reason": "Material not found"}

            file_bytes = b""
            filename = os.path.basename(file_path)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    file_bytes = f.read()

            rag_service = RAGService()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                num_chunks = loop.run_until_complete(
                    rag_service.ingest_material(file_bytes=file_bytes, filename=filename, metadata=metadata)
                )
            finally:
                loop.close()

            # Update material status to APPROVED or INDEXED
            material.status = "APPROVED"
            db.session.commit()

            logger.info(f"[Celery Indexing Task] Successfully indexed {num_chunks} chunks for material_id={material_id}")
            return {
                "status": "SUCCESS",
                "material_id": str(material_id),
                "chunks_indexed": num_chunks
            }

        except Exception as e:
            logger.error(f"[Celery Indexing Task Failed] Error: {e}")
            return {"status": "ERROR", "error": str(e)}
