"""
Scoring engine — orchestrates all four components.

Combines parseability (40), structure (20), keywords (25), content (15) into
a single 0-100 score, applies calibration, and produces the final
ScoringResult that the rest of the app consumes.

Calibration: We adjust the raw weighted score slightly to keep results
honest. A genuinely clean CV without a job ad should land in the 70-85 band;
with a matching job ad it can climb to 90+. Below 50 is reserved for CVs
with real structural problems. Above 95 is essentially impossible — there's
always something to improve, and reserving 95-100 for "perfect" keeps the
upsell honest. (This is a value commitment from the project memory, not
just a tuning decision.)
"""

from typing import Optional

from app.models import ScoringResult, StructuralIssue
from app.scoring.regions import detect_region
from app.scoring.parseability import score_parseability
from app.scoring.structure import score_structure
from app.scoring.keywords import score_keywords
from app.scoring.content import score_content


def run_scoring(
    cv_text: str,
    raw_bytes: bytes,
    content_type: str,
    job_description: str = "",
    region: str = "auto",
) -> ScoringResult:
    """
    Run the full scoring pipeline.

    Args:
        cv_text: Plain text extracted from the CV.
        raw_bytes: Original file bytes (for re-parsing parseability checks).
        content_type: MIME type of the original file.
        job_description: Optional job ad text.
        region: 'ZA' / 'UK' / 'US' / 'auto'.

    Returns:
        Complete ScoringResult ready for storage and/or response.
    """
    # ---- Region detection (used by structure and content scoring) ----
    haystack = f"{job_description}\n{cv_text}"
    region_profile = detect_region(haystack, explicit=region)

    # ---- Run each component ----
    parseability_score, parseability_issues = score_parseability(
        raw_text=cv_text,
        raw_bytes=raw_bytes,
        content_type=content_type,
    )

    structure_score, structure_issues = score_structure(
        cv_text=cv_text,
        region=region_profile,
    )

    keyword_score, missing_keywords, matched_keywords, keyword_source = score_keywords(
        cv_text=cv_text,
        job_description=job_description,
    )

    content_score, content_issues = score_content(
        cv_text=cv_text,
        region=region_profile,
    )

    # ---- Combine ----
    raw_score = parseability_score + structure_score + keyword_score + content_score

    # Calibration cap — keep above-95 reserved for genuinely outstanding CVs
    final_score = min(raw_score, 96)

    # ---- Aggregate issues ----
    all_issues = parseability_issues + structure_issues + content_issues

    # Sort by severity, then by penalty (worst first within each severity)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_issues.sort(
        key=lambda i: (severity_order.get(i.severity, 9), -i.penalty)
    )

    # ---- Rejection estimate based on score band ----
    rejection_estimate = _rejection_estimate_for(final_score)

    # ---- Augment missing-keywords list with metadata for the UI ----
    # The keyword_source lets the frontend say "from your job ad" or
    # "from the marketing baseline" — which is more useful than just a list.

    return ScoringResult(
        score=final_score,
        region=region_profile.code,
        rejection_estimate=rejection_estimate,
        structural_issues=all_issues,
        missing_keywords=missing_keywords,
        score_breakdown={
            "parseability": parseability_score,
            "parseability_max": 40,
            "structure": structure_score,
            "structure_max": 20,
            "keywords": keyword_score,
            "keywords_max": 25,
            "keyword_source": keyword_source,
            "matched_keywords": matched_keywords,
            "content": content_score,
            "content_max": 15,
            "raw_total": raw_score,
            "calibrated_total": final_score,
        },
    )


def _rejection_estimate_for(score: int) -> int:
    """
    Honest rejection-rate estimate by score band. Calibrated to be roughly
    consistent with public ATS-rejection studies; will be refined once we
    have data from the first batch of paid scans.
    """
    if score >= 90:
        return 8
    if score >= 80:
        return 18
    if score >= 70:
        return 32
    if score >= 60:
        return 48
    if score >= 50:
        return 62
    if score >= 40:
        return 75
    return 86
