"""GroundingVerifier — deterministic grounding assessment for AI answers.

Classifies whether an AI answer is supported by the retrieved context.

Statuses:
    SUPPORTED           — answer is well-grounded in retrieved evidence
    PARTIALLY_SUPPORTED — answer has partial overlap with retrieved content
    UNSUPPORTED         — answer shows little/no evidence from retrieved context

Algorithm (deterministic, no LLM call):
    1. Tokenize answer and context to meaningful words (alpha, length ≥ MIN_WORD_LEN).
    2. Compute overlap ratio = |answer_words ∩ context_words| / |answer_words|.
    3. Apply threshold mapping.

Thresholds:
    overlap_ratio ≥ SUPPORTED_THRESHOLD         → SUPPORTED
    overlap_ratio ≥ PARTIALLY_SUPPORTED_THRESHOLD → PARTIALLY_SUPPORTED
    otherwise                                     → UNSUPPORTED

Special cases:
    - Empty or very short answer  → SUPPORTED (trivially satisfied)
    - No context retrieved        → UNSUPPORTED (never claim support without evidence)
    - Answer shorter than MIN_MEANINGFUL_WORDS → SUPPORTED (short ack/no-context responses)

The overlap is checked against STOPWORDS to avoid high scores from common words.

This is a HEURISTIC — it approximates grounding based on lexical overlap.
It is NOT a semantic entailment model. Re-calibrate thresholds with real data.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
# Documented as heuristics. Re-calibrate with real answer/context pairs.
SUPPORTED_THRESHOLD = 0.35
PARTIALLY_SUPPORTED_THRESHOLD = 0.10

# Words shorter than this are excluded from overlap analysis
MIN_WORD_LEN = 4

# Minimum number of meaningful words in the answer before we apply grounding check.
# Very short answers (e.g. "I don't know") are trivially marked SUPPORTED to avoid
# false UNSUPPORTED verdicts on safe no-context fallback responses.
MIN_MEANINGFUL_WORDS = 5

# Common words that should NOT count toward grounding overlap
STOPWORDS = frozenset({
    "this", "that", "with", "from", "have", "will", "your", "which",
    "they", "been", "were", "their", "what", "when", "also", "some",
    "about", "these", "those", "into", "than", "then", "only", "more",
    "both", "each", "such", "after", "there", "here", "very", "just",
    "because", "however", "therefore", "according", "material", "document",
    "content", "information", "provided", "based", "using", "study",
    "question", "answer", "following", "section", "chapter",
})


class GroundingVerifier:
    """Assess whether an AI answer is grounded in the retrieved context.

    Usage::

        verifier = GroundingVerifier()
        status = verifier.verify(answer="...", context="...")
        # "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED"

    Both answer and context are the plain text strings (not formatted with fences).
    """

    def verify(
        self,
        answer: str,
        context: str,
        grounding_available: bool = True,
    ) -> str:
        """Classify grounding of answer relative to context.

        Args:
            answer:   The AI-generated answer text.
            context:  The raw context text passed to the LLM (without DATA fence wrappers).
            grounding_available: Set to False when no context was retrieved at all.
                                 Forces UNSUPPORTED regardless of answer content.

        Returns:
            "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED"
        """
        # No context retrieved → answer cannot be supported
        if not grounding_available or not (context or "").strip():
            return "UNSUPPORTED"

        answer_words = _meaningful_words(answer or "")

        # Very short or empty answer — treat as supported (e.g. safe fallback messages)
        if len(answer_words) < MIN_MEANINGFUL_WORDS:
            return "SUPPORTED"

        context_words = _meaningful_words(context or "")

        overlap = len(answer_words & context_words)
        ratio = overlap / len(answer_words)

        if ratio >= SUPPORTED_THRESHOLD:
            return "SUPPORTED"
        if ratio >= PARTIALLY_SUPPORTED_THRESHOLD:
            return "PARTIALLY_SUPPORTED"
        return "UNSUPPORTED"

    def verify_from_sources(
        self,
        answer: str,
        sources: list,
    ) -> str:
        """Convenience wrapper: build context from source snippets, then verify.

        Args:
            answer:  The AI-generated answer text.
            sources: List of citation dicts (from RAGService or CitationVerifier),
                     each with a ``"snippet"`` or ``"excerpt"`` key.
        """
        if not sources:
            return self.verify(answer=answer, context="", grounding_available=False)
        context = " ".join(
            str(s.get("snippet") or s.get("excerpt") or "") for s in sources
        )
        return self.verify(answer=answer, context=context, grounding_available=bool(context.strip()))


def _meaningful_words(text: str) -> frozenset:
    """Tokenise text to a set of meaningful lowercase words."""
    words = re.findall(r"[a-zA-Z]+", text)
    return frozenset(
        w.lower()
        for w in words
        if len(w) >= MIN_WORD_LEN and w.lower() not in STOPWORDS
    )
