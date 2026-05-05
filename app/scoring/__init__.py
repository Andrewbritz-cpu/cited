"""
Cited scoring package.

Public entry point: `score_cv(...)` — keeps the same signature as the old
stub so the rest of the app needs no changes.
"""

from app.scoring.engine import run_scoring
from app.models import ScoringResult


def score_cv(
    cv_text: str,
    raw_bytes: bytes = b"",
    content_type: str = "application/pdf",
    job_description: str = "",
    region: str = "auto",
) -> ScoringResult:
    """
    Score a CV. Heuristic-only, no LLM calls, no API costs.

    Args:
        cv_text: Plain text extracted from the user's CV.
        raw_bytes: Original file bytes — required for full parseability
            analysis. If empty, parseability scoring uses text-only signals
            (still useful but less precise on PDF-specific issues).
        content_type: MIME type of the original file.
        job_description: Optional job ad to score keyword fit against.
        region: 'ZA' / 'UK' / 'US' / 'auto'. When 'auto', inferred from
            content signals.

    Returns:
        ScoringResult with score (0-100), region, rejection estimate,
        structural issues, missing keywords, and full score breakdown.
    """
    return run_scoring(
        cv_text=cv_text,
        raw_bytes=raw_bytes,
        content_type=content_type,
        job_description=job_description,
        region=region,
    )


__all__ = ["score_cv", "ScoringResult"]
