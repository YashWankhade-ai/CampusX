"""Celery task: asynchronous document indexing pipeline.

Security contract:
    - institution_id is ALWAYS read from the DB (material.author.institution_id).
      It is NEVER trusted from the caller-supplied metadata dict.
    - The task aborts if material is not found, is deleted, or is not in APPROVED status.
    - The task NEVER auto-approves a material.
    - Exceptions are caught and logged without exposing tracebacks or secrets.

Lifecycle:
    Dispatcher (ApprovalService.approve_material):
        db.commit() → index_document_task.delay(material_id, metadata)

    This task:
        1. Re-fetch material from DB (verify APPROVED + not deleted)
        2. Build institution_id from material.author.institution_id (DB, not metadata)
        3. Read file bytes from storage_path in the latest MaterialVersion
        4. ingest_material() → extract → chunk → embed → Qdrant upsert
        5. Leave material status as APPROVED (never auto-approve)

Context handling:
    - When called from a Celery worker there is no Flask app context — we create one.
    - When called directly in tests (within an existing app context) we reuse it.
"""
import os
import uuid
import asyncio
import logging

from .celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="tasks.index_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def index_document_task(self, material_id: str, metadata: dict):
    """Index an APPROVED study material into the Qdrant vector store.

    Args:
        material_id: UUID string of the StudyMaterial to index.
        metadata: Hint metadata dict (institution_id is always re-fetched from DB).

    Returns:
        dict with status, material_id, chunks_indexed keys.
    """
    # Deferred imports — avoid circular import at module level
    from app import create_app
    from app.extensions import db
    from app.models.resource import StudyMaterial, MaterialVersion
    from app.models.user import User
    from app.services.ai.rag_service import RAGService

    # Support both Celery worker invocation (no app context) and
    # direct test invocation (existing app context already active).
    ctx = None
    try:
        from flask import current_app
        current_app._get_current_object()  # raises RuntimeError if no context
    except RuntimeError:
        _app = create_app("production")
        ctx = _app.app_context()
        ctx.push()

    try:
        logger.info("[Indexing] Starting: material_id=%s", material_id)

        # 1. Validate material_id format
        try:
            mat_uuid = uuid.UUID(str(material_id))
        except (ValueError, TypeError):
            logger.error("[Indexing] Invalid material_id format: %s", material_id)
            return {"status": "FAILED", "reason": "Invalid material_id"}

        # 2. Re-fetch from DB
        material = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()
        if not material:
            logger.error("[Indexing] Material not found: %s", material_id)
            return {"status": "FAILED", "reason": "Material not found"}

        # 3. Abort if soft-deleted
        if getattr(material, "is_deleted", False):
            logger.warning("[Indexing] Material is deleted — skipping: %s", material_id)
            return {"status": "SKIPPED", "reason": "Material is deleted"}

        # 4. Abort if not APPROVED — only process approved content
        if material.status != "APPROVED":
            logger.warning(
                "[Indexing] Material status is %r (not APPROVED) — skipping: %s",
                material.status, material_id,
            )
            return {"status": "SKIPPED", "reason": f"Material status is {material.status!r}"}

        # 5. Resolve institution_id from DB — NEVER from caller-supplied metadata
        author = db.session.query(User).filter_by(id=material.author_id).first()
        if not author:
            logger.error("[Indexing] Author not found for material: %s", material_id)
            return {"status": "FAILED", "reason": "Author not found"}

        institution_id = str(author.institution_id) if author.institution_id else ""
        if not institution_id:
            logger.warning("[Indexing] Author has no institution_id — empty isolation key")

        # 6. Read file bytes from the latest MaterialVersion → FileMetadata.storage_path
        file_bytes = b""
        filename = metadata.get("filename", f"{material_id}.bin")
        mime_type = metadata.get("mime_type", "")

        latest_version = (
            db.session.query(MaterialVersion)
            .filter_by(study_material_id=mat_uuid)
            .order_by(MaterialVersion.version_number.desc())
            .first()
        )
        if latest_version and latest_version.file_metadata:
            file_meta = latest_version.file_metadata
            storage_path = file_meta.storage_path
            filename = file_meta.original_name or filename
            mime_type = file_meta.mime_type or mime_type

            if os.path.exists(storage_path):
                try:
                    with open(storage_path, "rb") as fh:
                        file_bytes = fh.read()
                except OSError as exc:
                    logger.warning(
                        "[Indexing] Could not read file at %s: %s — empty bytes",
                        storage_path, type(exc).__name__,
                    )
            else:
                logger.warning(
                    "[Indexing] Storage path missing: %s — empty bytes", storage_path
                )

        # 7. Build Qdrant payload metadata — institution_id and approval flags from DB
        qdrant_metadata = {
            "document_id": str(material.id),
            "institution_id": institution_id,            # From DB — tamper-proof
            "author_id": str(material.author_id),
            "subject_id": str(material.subject_id) if material.subject_id else "",
            "title": material.title,
            "material_type": (
                material.material_type.value
                if hasattr(material.material_type, "value")
                else str(material.material_type)
            ),
            "mime_type": mime_type,
            "filename": filename,
            "is_approved": material.status == "APPROVED",   # True — verified above
            "is_deleted": bool(getattr(material, "is_deleted", False)),
            "allowed_roles": ["STUDENT", "FACULTY", "MODERATOR", "INSTITUTION_ADMIN", "SUPER_ADMIN"],
        }

        # 8. Run the async ingest pipeline in a new event loop
        rag_service = RAGService()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            num_chunks = loop.run_until_complete(
                rag_service.ingest_material(
                    file_bytes=file_bytes,
                    filename=filename,
                    metadata=qdrant_metadata,
                )
            )
        finally:
            loop.close()

        # 9. Refresh session — do NOT change approval status
        db.session.refresh(material)
        db.session.commit()

        logger.info(
            "[Indexing] Complete: material_id=%s institution_id=%s chunks=%d",
            material_id, institution_id, num_chunks,
        )
        return {
            "status": "SUCCESS",
            "material_id": str(material_id),
            "institution_id": institution_id,
            "chunks_indexed": num_chunks,
        }

    except Exception as exc:
        logger.error(
            "[Indexing] Unexpected error for material_id=%s: %s",
            material_id, type(exc).__name__,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[Indexing] Max retries exceeded for material_id=%s", material_id)
            return {"status": "ERROR", "reason": "Max retries exceeded"}
        except Exception:
            return {"status": "ERROR", "reason": "Indexing failed"}

    finally:
        # Pop the context we pushed — don't pop if it was already active
        if ctx is not None:
            ctx.pop()
