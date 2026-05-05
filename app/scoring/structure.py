"""
Structure scoring (20% of total score).

This component checks whether the CV has the conventional building blocks
that ATS systems and recruiters expect:
- Recognisable section headers (Experience, Education, Skills, etc.)
- Contact details near the top
- Date ranges that mark employment periods
- Region-appropriate phone format

Unlike parseability, structure issues are usually fixable without redesigning
the CV — they're about the *content layout* rather than the file format.
"""

import re
from typing import List, Tuple

from app.models import StructuralIssue
from app.scoring.regions import RegionProfile


# Standard CV section header words. We match case-insensitively and allow
# variants ("WORK EXPERIENCE", "Professional Experience", etc.)
SECTION_HEADERS = {
    "experience": [
        "experience", "work history", "employment history",
        "professional experience", "career history",
    ],
    "education": [
        "education", "academic", "qualifications", "academic background",
    ],
    "skills": [
        "skills", "competencies", "technical skills", "core competencies",
        "key skills", "expertise",
    ],
    "summary": [
        "summary", "professional summary", "profile", "objective",
        "personal statement", "career objective",
    ],
}


def score_structure(
    cv_text: str,
    region: RegionProfile,
) -> Tuple[int, List[StructuralIssue]]:
    """
    Score the CV's structural completeness out of 20 points.
    """
    issues: List[StructuralIssue] = []
    text_lower = cv_text.lower()

    # ---- A: section headers ----
    sections_found = _count_sections_present(text_lower)
    if sections_found == 0:
        issues.append(StructuralIssue(
            severity="critical",
            type="no_recognisable_sections",
            description=(
                "No standard CV section headers detected (Experience, "
                "Education, Skills, etc.). ATS systems use these headers to "
                "categorise your information; without them, content can't be "
                "indexed properly."
            ),
            penalty=12,
        ))
    elif sections_found == 1:
        issues.append(StructuralIssue(
            severity="high",
            type="few_section_headers",
            description=(
                "Only one standard section header detected. Most ATS systems "
                "expect at least Experience, Education, and Skills sections; "
                "labelled headers help ensure information is correctly bucketed."
            ),
            penalty=8,
        ))
    elif sections_found == 2:
        issues.append(StructuralIssue(
            severity="medium",
            type="missing_section_headers",
            description=(
                "Two standard section headers detected. Adding a 'Skills' or "
                "'Summary' section helps ATS systems index your CV more accurately."
            ),
            penalty=4,
        ))

    # ---- B: contact details near the top ----
    first_chunk = cv_text[:800]
    has_email = bool(re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", first_chunk))
    has_phone = _has_phone_number(first_chunk, region)

    if not has_email and not has_phone:
        issues.append(StructuralIssue(
            severity="critical",
            type="no_contact_details_at_top",
            description=(
                "No email or phone number found in the first 800 characters. "
                "ATS systems specifically look for contact details near the top; "
                "without them, your CV may be classified as incomplete."
            ),
            penalty=10,
        ))
    elif not has_email:
        issues.append(StructuralIssue(
            severity="high",
            type="no_email_at_top",
            description=(
                "No email address found near the top of the CV. ATS systems "
                "use the email as the primary candidate identifier."
            ),
            penalty=6,
        ))
    elif not has_phone:
        issues.append(StructuralIssue(
            severity="medium",
            type="no_phone_at_top",
            description=(
                f"No {region.code}-format phone number found near the top of the CV. "
                "Recruiters often filter by phone availability for time-sensitive roles."
            ),
            penalty=4,
        ))

    # ---- C: date ranges ----
    # Real CVs have at least 2-3 year markers (start/end of jobs and education)
    year_count = len(set(re.findall(r"\b(?:19|20)\d{2}\b", cv_text)))
    if year_count == 0:
        issues.append(StructuralIssue(
            severity="high",
            type="no_dates_at_all",
            description=(
                "No year-based dates detected anywhere in the CV. ATS systems "
                "use date ranges to compute total years of experience — without "
                "them, your CV will likely be filtered out of experience-based searches."
            ),
            penalty=8,
        ))
    elif year_count < 3:
        issues.append(StructuralIssue(
            severity="medium",
            type="few_date_markers",
            description=(
                f"Only {year_count} distinct year(s) detected. Most CVs include "
                "start and end years for each role and qualification; sparse "
                "dating makes employment history hard for ATS systems to map."
            ),
            penalty=4,
        ))

    # ---- D: region-mismatched phone format ----
    if has_phone:
        wrong_region_phone = _detects_wrong_region_phone(first_chunk, region)
        if wrong_region_phone:
            issues.append(StructuralIssue(
                severity="low",
                type="phone_format_region_mismatch",
                description=(
                    f"Phone number doesn't match {region.code} convention "
                    f"({region.name}). Some ATS filters parse and validate "
                    "phone numbers by region; non-standard format may cause "
                    "issues for region-specific recruiter searches."
                ),
                penalty=3,
            ))

    # ---- Final score ----
    total_penalty = sum(issue.penalty for issue in issues)
    score = max(20 - total_penalty, 0)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda i: severity_order.get(i.severity, 9))

    return score, issues


def _count_sections_present(text_lower: str) -> int:
    """Count how many of the four canonical sections are detected."""
    count = 0
    for variants in SECTION_HEADERS.values():
        if any(v in text_lower for v in variants):
            count += 1
    return count


def _has_phone_number(text: str, region: RegionProfile) -> bool:
    """Match against the region's preferred phone patterns OR a generic fallback."""
    for pattern in region.phone_patterns:
        if re.search(pattern, text):
            return True
    # Generic international fallback — at least 7 digits with optional formatting
    return bool(re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text))


def _detects_wrong_region_phone(text: str, expected_region: RegionProfile) -> bool:
    """
    Returns True if the only phone number we can find matches a *different*
    region's convention. Used to flag e.g. a US +1 number on a CV otherwise
    detected as ZA.
    """
    from app.scoring.regions import PROFILES

    # Did the expected region's pattern match?
    expected_match = any(
        re.search(p, text) for p in expected_region.phone_patterns
    )
    if expected_match:
        return False

    # Did some *other* region's pattern match?
    for code, profile in PROFILES.items():
        if code == expected_region.code:
            continue
        if any(re.search(p, text) for p in profile.phone_patterns):
            return True

    return False
