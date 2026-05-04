"""
Scoring engine adapter.

This is the one file you'll modify to plug in your existing Python ATS scoring
tool (the v3 with ZA/UK/US regional profiles). The rest of the app calls
`score_cv()` and only cares about the shape of the returned ScoringResult.

To integrate your real scorer:
    1. Copy your existing scoring module into `app/legacy_scorer.py`
       (or wherever you prefer to keep it).
    2. Replace the body of `score_cv()` below with a call into your scorer,
       mapping its output to the ScoringResult fields.

The placeholder implementation below uses simple heuristics + Claude API for
keyword extraction so the project runs end-to-end before integration. Treat it
as a development stub.
"""

import os
import re
from typing import List

from anthropic import Anthropic

from app.models import ScoringResult, StructuralIssue


# -------------------- Public API --------------------

def score_cv(
    cv_text: str,
    job_description: str = "",
    region: str = "auto",
) -> ScoringResult:
    """
    Score a CV against ATS parsing rules and (optionally) a target job ad.

    Args:
        cv_text: Plain text extracted from the user's CV.
        job_description: Optional job ad to score keyword fit against.
        region: 'ZA', 'UK', 'US', or 'auto'. When 'auto', infers from job ad.

    Returns:
        ScoringResult with score (0–100), structural issues, missing keywords,
        and rejection estimate.
    """
    resolved_region = _resolve_region(region, job_description, cv_text)

    structural_issues = _detect_structural_issues(cv_text)
    structural_penalty = sum(issue.penalty for issue in structural_issues)

    missing_keywords: List[str] = []
    keyword_penalty = 0
    if job_description.strip():
        missing_keywords = _find_missing_keywords(cv_text, job_description)
        # Cap the keyword penalty so a single bad job-ad match can't tank a
        # technically-clean CV. 3 points per missing keyword, max 30.
        keyword_penalty = min(len(missing_keywords) * 3, 30)

    # Base score is 100; subtract penalties.
    raw_score = 100 - structural_penalty - keyword_penalty
    score = max(min(raw_score, 100), 0)

    rejection_estimate = _rejection_estimate_for(score)

    return ScoringResult(
        score=score,
        region=resolved_region,
        rejection_estimate=rejection_estimate,
        structural_issues=structural_issues,
        missing_keywords=missing_keywords,
        score_breakdown={
            "base": 100,
            "structural_penalty": structural_penalty,
            "keyword_penalty": keyword_penalty,
        },
    )


# -------------------- Internal helpers --------------------

def _resolve_region(region: str, job_description: str, cv_text: str) -> str:
    """Auto-detect region from currency, phone format, or location markers."""
    if region.upper() in {"ZA", "UK", "US"}:
        return region.upper()

    haystack = f"{job_description}\n{cv_text}".lower()

    za_signals = ["south africa", "johannesburg", "cape town", "durban",
                  "pretoria", "+27", "zar ", " r ", "saqa", "b-bbee"]
    uk_signals = ["united kingdom", "london", "manchester", "+44",
                  "£", "gbp", "ltd ", "ucas"]
    us_signals = ["united states", "new york", "san francisco", "+1 ",
                  "$", "usd", " llc", "401k"]

    counts = {
        "ZA": sum(1 for s in za_signals if s in haystack),
        "UK": sum(1 for s in uk_signals if s in haystack),
        "US": sum(1 for s in us_signals if s in haystack),
    }
    best = max(counts, key=counts.get)
    # Default to ZA if everything ties on zero — this is a SA tool first.
    return best if counts[best] > 0 else "ZA"


def _detect_structural_issues(cv_text: str) -> List[StructuralIssue]:
    """
    Heuristic structural issue detection.

    These are the issues real ATS systems trip on. Replace with your existing
    scorer's logic — these heuristics are intentionally simple stubs.
    """
    issues: List[StructuralIssue] = []

    # Excessive whitespace / column collapse — strong signal of multi-column layout
    multiple_spaces = re.findall(r" {4,}", cv_text)
    if len(multiple_spaces) > 10:
        issues.append(StructuralIssue(
            severity="high",
            type="multi_column_layout",
            description="Multi-column layout detected — most ATS systems read top-to-bottom in a single column and will jumble multi-column content.",
            penalty=15,
        ))

    # No clear section headers
    standard_headers = ["experience", "education", "skills", "summary", "profile"]
    found = sum(1 for h in standard_headers if h in cv_text.lower())
    if found < 2:
        issues.append(StructuralIssue(
            severity="high",
            type="missing_section_headers",
            description="Missing or unclear section headers. ATS systems use headers like 'Experience' and 'Education' to bucket your information.",
            penalty=12,
        ))

    # Contact details near the top
    first_chunk = cv_text[:600].lower()
    has_email = "@" in first_chunk
    has_phone = bool(re.search(r"(\+?\d[\d\s\-()]{7,})", first_chunk))
    if not (has_email and has_phone):
        issues.append(StructuralIssue(
            severity="medium",
            type="contact_details_missing",
            description="Contact details (email and phone) should appear near the top of the CV. ATS systems specifically look for them there.",
            penalty=8,
        ))

    # Very long unparseable runs (often indicates text inside images or tables)
    if len(cv_text) < 500:
        issues.append(StructuralIssue(
            severity="critical",
            type="low_text_extraction",
            description="Very little extractable text — the CV may rely on images, tables, or text boxes. ATS systems will see almost nothing.",
            penalty=30,
        ))

    # Date format consistency
    if re.search(r"\b\d{4}\b", cv_text) is None:
        issues.append(StructuralIssue(
            severity="medium",
            type="missing_dates",
            description="No clear year-based dates found. ATS systems use date ranges to compute years of experience.",
            penalty=6,
        ))

    return issues


def _find_missing_keywords(cv_text: str, job_description: str) -> List[str]:
    """
    Use Claude to extract the top keywords from the job ad and return those
    missing from the CV. This is the single AI-powered step in the scorer.

    For production volume, consider caching by job-ad hash to keep API costs down.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Fall back to a naive bag-of-nouns approach if no API key is configured.
        return _naive_missing_keywords(cv_text, job_description)

    client = Anthropic(api_key=api_key)
    prompt = f"""You are extracting ATS keywords from a job description.

Return a JSON array of the 15 most important hard-skill keywords or domain terms
the ATS will be scanning for. Prefer specific technical terms, certifications,
tools, and methodologies over generic words like "leadership" or "communication".

Job description:
---
{job_description[:3000]}
---

Respond with ONLY a JSON array of strings, no other text. Example:
["AWS", "Kubernetes", "CI/CD pipelines", "Terraform", "PostgreSQL"]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip code fences if Claude added them
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
        import json
        keywords = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[scorer] Claude keyword extraction failed: {exc} — falling back")
        return _naive_missing_keywords(cv_text, job_description)

    cv_lower = cv_text.lower()
    missing = [kw for kw in keywords if kw.lower() not in cv_lower]
    return missing[:10]


def _naive_missing_keywords(cv_text: str, job_description: str) -> List[str]:
    """Fallback when no Claude API key is configured."""
    job_words = set(re.findall(r"\b[A-Za-z]{4,}\b", job_description.lower()))
    cv_words = set(re.findall(r"\b[A-Za-z]{4,}\b", cv_text.lower()))
    stopwords = {"experience", "ability", "working", "skills", "looking", "candidate",
                 "company", "team", "role", "position", "include", "responsibilities",
                 "requirements", "preferred", "essential", "manage", "ensure"}
    missing = [w for w in job_words - cv_words - stopwords if len(w) >= 5]
    return sorted(missing)[:10]


def _rejection_estimate_for(score: int) -> int:
    """
    Empirical rejection-rate estimate based on score.

    Replace with your real model once you have data from the SA AI Visibility
    work or the first 100 paid scans.
    """
    if score >= 85:
        return 12
    if score >= 70:
        return 28
    if score >= 55:
        return 47
    if score >= 40:
        return 68
    return 84
