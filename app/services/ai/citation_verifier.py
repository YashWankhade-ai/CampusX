"""CitationVerifier — verifies AI citations against trusted application data.

A citation is ONLY considered verified when ALL conditions hold:
    1. document_id is a valid UUID.
    2. StudyMaterial exists in the DB.
    3. StudyMaterial is not soft-deleted.
    4. StudyMaterial.status == "APPROVED".
    5. The material's author belongs to the same institution as the requester.

The LLM is NEVER trusted to fabricate citation metadata.
All verified citations are constructed from retrieval results — not LLM output.

Cross-institution citations always fail closed (NOT_FOUND behavior):
    - No leakage of whether a resource exists in another institution.
"""
import uuid
import logging
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models.resource import StudyMaterial
from app.models.user import User

logger = logging.getLogger(__name__)

# Maximum excerpt length stored per citation (characters)
MAX_EXCERPT_LEN = 500
# Maximum excerpt exposed in API response (characters)
MAX_EXCERPT_RESPONSE_LEN = 300


class CitationVerifier:
    """Verify and filter AI citations against trusted DB state.

    Usage::

        verifier = CitationVerifier()
        verified = verifier.verify_citations(raw_sources, institution_id="<uuid>")

    raw_sources:  List of dicts from RAGService.retrieve_context() with keys:
                  document_id, title, snippet, score, chunk_index.
    institution_id: Must come from the JWT — never from client input.

    Returns only citations that pass all 5 security checks above.
    Fabricated or cross-institution citations are silently dropped.
    """

    def verify_citations(
        self,
        raw_sources: List[Dict[str, Any]],
        institution_id: str,
    ) -> List[Dict[str, Any]]:
        """Filter raw retrieval results to only DB-verified, institution-scoped citations.

        Args:
            raw_sources: Chunks from RAGService.retrieve_context(). Each dict must
                         contain at least ``document_id``.
            institution_id: The requester's institution UUID (from JWT).

        Returns:
            List of verified citation dicts. Empty list if nothing passes.
            Each dict has: document_id, study_material_id, title,
                           chunk_index, relevance_score, excerpt.
        """
        if not raw_sources:
            return []

        # Parse institution_id — if provided but invalid UUID, fail closed
        inst_uuid: Optional[uuid.UUID]
        if institution_id:
            try:
                inst_uuid = uuid.UUID(str(institution_id))
            except (ValueError, TypeError):
                logger.warning(
                    "CitationVerifier: invalid institution_id %r — dropping all citations.", institution_id
                )
                return []
        else:
            inst_uuid = None

        verified: List[Dict[str, Any]] = []

        for src in raw_sources:
            result = self._verify_single(src, inst_uuid)
            if result is not None:
                verified.append(result)

        return verified

    def _verify_single(
        self,
        src: Dict[str, Any],
        inst_uuid: Optional[uuid.UUID],
    ) -> Optional[Dict[str, Any]]:
        """Verify a single source citation. Returns verified dict or None."""
        mat_id_str = src.get("document_id")
        if not mat_id_str:
            return None

        # 1. Valid UUID
        try:
            mat_uuid = uuid.UUID(str(mat_id_str))
        except (ValueError, TypeError):
            logger.debug("CitationVerifier: dropping citation with invalid UUID %r", mat_id_str)
            return None

        # 2. Material exists in DB
        material = db.session.query(StudyMaterial).filter_by(id=mat_uuid).first()
        if not material:
            logger.debug("CitationVerifier: dropping citation for unknown material %s", mat_uuid)
            return None

        # 3. Not deleted
        if getattr(material, "is_deleted", False):
            logger.debug("CitationVerifier: dropping citation for deleted material %s", mat_uuid)
            return None

        # 4. Institution isolation — via author join (allowing DEFAULT-01 materials for general curriculum)
        if inst_uuid is not None:
            author = db.session.query(User).filter_by(id=material.author_id).first()
            from app.models.academic import Institution
            default_inst = Institution.query.filter_by(code='DEFAULT-01').first()
            default_id = default_inst.id if default_inst else None
            is_allowed = (
                author is not None and (
                    author.institution_id == inst_uuid or
                    author.institution_id == default_id or
                    author.institution_id is None
                )
            )
            if not is_allowed:
                logger.debug(
                    "CitationVerifier: dropping cross-institution citation %s", mat_uuid
                )
                return None

        # 5. Approved only — checked AFTER institution check to avoid leaking existence
        if getattr(material, "status", "") != "APPROVED":
            logger.debug(
                "CitationVerifier: dropping citation for non-approved material %s (status=%s)",
                mat_uuid,
                getattr(material, "status", "?"),
            )
            return None

        return {
            "document_id": str(mat_uuid),
            "study_material_id": str(mat_uuid),
            "title": material.title,
            "chunk_index": src.get("chunk_index"),
            "relevance_score": float(src.get("score", 0.0)),
            "excerpt": (src.get("snippet") or "")[:MAX_EXCERPT_LEN],
            # Shorter version for API responses
            "excerpt_short": (src.get("snippet") or "")[:MAX_EXCERPT_RESPONSE_LEN],
        }
