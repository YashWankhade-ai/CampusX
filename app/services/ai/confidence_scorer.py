"""ConfidenceScorer — multi-signal, deterministic confidence scoring for AI responses.

Replaces the single-signal RAGService.calculate_confidence() with a richer model
that combines retrieval quality, source diversity, and grounding status.

Score: 0.0–1.0 (float, rounded to 3 decimal places)
Level: "low" | "medium" | "high"

Thresholds:
    0.00–0.39 → low
    0.40–0.69 → medium
    0.70–1.00 → high

Formula (all inputs normalised to 0.0–1.0 before weighting):

    Signal              Weight   Description
    ─────────────────   ──────   ─────────────────────────────────────────────
    top_score_norm      0.40     Top RRF score, normalised relative to 2× HIGH threshold
    avg_score_norm      0.25     Mean RRF score of all retrieved chunks
    chunk_factor        0.20     Chunk count (saturates at N_CHUNKS_SATURATION)
    diversity_factor    0.15     Unique source documents (saturates at N_SOURCES_SATURATION)
    ─────────────────   ──────
    raw                 1.00     Sum of weighted signals

Grounding adjustment (applied AFTER weighted sum):
    SUPPORTED           → +0.10   (answer is backed by evidence)
    PARTIALLY_SUPPORTED → -0.05   (some support but weak)
    UNSUPPORTED         → -0.20   (answer not supported by retrieved context)
    None / unknown      →  0.00   (no grounding information available)

Final score = clip(raw + adjustment, 0.0, 1.0)

All thresholds are documented as heuristics — not calibrated probabilities.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Normalization constants ────────────────────────────────────────────────────
# RRF HIGH threshold from prompt_templates is 0.03.
# We use 2× that (0.06) as the "perfect" normalisation anchor.
_RRF_NORM_TOP = 0.06
_RRF_NORM_AVG = 0.04

# Chunk count at which the chunk_factor signal saturates to 1.0
N_CHUNKS_SATURATION = 5

# Unique-source count at which diversity_factor saturates to 1.0
N_SOURCES_SATURATION = 3

# ── Level thresholds ───────────────────────────────────────────────────────────
# Documented explicitly as heuristics.
LEVEL_THRESHOLDS = {
    "high": 0.70,
    "medium": 0.40,
    # below medium → "low"
}

# ── Signal weights ─────────────────────────────────────────────────────────────
_W_TOP = 0.40
_W_AVG = 0.25
_W_CHUNKS = 0.20
_W_DIVERSITY = 0.15

# ── Grounding adjustments ──────────────────────────────────────────────────────
_GROUNDING_DELTA = {
    "SUPPORTED": 0.10,
    "PARTIALLY_SUPPORTED": -0.05,
    "UNSUPPORTED": -0.20,
}


class ConfidenceScorer:
    """Compute a deterministic, multi-signal confidence score.

    Usage::

        scorer = ConfidenceScorer()
        result = scorer.score(sources, grounding_status="SUPPORTED")
        # result = {"score": 0.784, "level": "high"}

    ``sources`` is the list returned by CitationVerifier.verify_citations()
    (or the raw RAGService sources list).  Each entry must have a ``"score"``
    key with the RRF relevance score.

    ``grounding_status`` is the string returned by GroundingVerifier.verify().
    Pass None when grounding is not available.
    """

    def score(
        self,
        sources: List[Dict[str, Any]],
        grounding_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute confidence score and level.

        Returns::

            {
                "score": float,        # 0.0–1.0
                "level": str,          # "low" | "medium" | "high"
                "signals": {           # diagnostic breakdown
                    "top_score": float,
                    "avg_score": float,
                    "chunk_count": int,
                    "unique_sources": int,
                    "grounding_status": str | None,
                }
            }
        """
        if not sources:
            raw = 0.0
            top_raw = 0.0
            avg_raw = 0.0
            n_chunks = 0
            n_unique = 0
        else:
            scores = [float(s.get("score", 0.0)) for s in sources]
            top_raw = scores[0] if scores else 0.0
            avg_raw = sum(scores) / len(scores)
            n_chunks = len(sources)

            # Count unique source documents
            unique_docs = {s.get("document_id") for s in sources if s.get("document_id")}
            n_unique = len(unique_docs)

            # Normalise each signal to [0, 1]
            norm_top = min(top_raw / _RRF_NORM_TOP, 1.0) if _RRF_NORM_TOP > 0 else 0.0
            norm_avg = min(avg_raw / _RRF_NORM_AVG, 1.0) if _RRF_NORM_AVG > 0 else 0.0
            chunk_factor = min(n_chunks / N_CHUNKS_SATURATION, 1.0)
            diversity_factor = min(n_unique / N_SOURCES_SATURATION, 1.0)

            raw = (
                _W_TOP * norm_top
                + _W_AVG * norm_avg
                + _W_CHUNKS * chunk_factor
                + _W_DIVERSITY * diversity_factor
            )

        # Apply grounding adjustment
        delta = _GROUNDING_DELTA.get(grounding_status or "", 0.0)
        final = max(0.0, min(1.0, raw + delta))
        final = round(final, 3)

        level = _score_to_level(final)

        return {
            "score": final,
            "level": level,
            "signals": {
                "top_score": round(top_raw if sources else 0.0, 6),
                "avg_score": round(avg_raw if sources else 0.0, 6),
                "chunk_count": n_chunks if sources else 0,
                "unique_sources": n_unique if sources else 0,
                "grounding_status": grounding_status,
            },
        }


def _score_to_level(score: float) -> str:
    """Map a 0.0–1.0 float to a level label."""
    if score >= LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"
