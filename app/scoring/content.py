"""
Content quality scoring (15% of total score).

This component scores the *writing* of the CV — independent of structure
and keywords. It checks:
- Bullet point usage (ATSs and recruiters prefer scannable bullets to walls of text)
- Action verb usage (CVs led by strong verbs read better and parse better)
- Quantified achievements (numbers signal substance)
- Length (too short = thin; too long = unfocused)
- Pronoun overuse (CVs shouldn't contain "I" / "my" — too informal)
"""

import re
from typing import List, Tuple

from app.models import StructuralIssue
from app.scoring.regions import RegionProfile


# A curated list of strong action verbs that appear in well-written CV bullets
ACTION_VERBS = {
    "led", "managed", "directed", "drove", "delivered", "implemented",
    "launched", "built", "developed", "designed", "created", "established",
    "executed", "produced", "achieved", "exceeded", "increased", "reduced",
    "improved", "transformed", "streamlined", "optimised", "optimized",
    "negotiated", "secured", "won", "generated", "raised", "saved",
    "automated", "scaled", "grew", "expanded", "consolidated",
    "introduced", "pioneered", "spearheaded", "championed",
    "coordinated", "supervised", "trained", "mentored", "coached",
    "analysed", "analyzed", "researched", "investigated", "evaluated",
    "presented", "published", "authored", "co-authored",
    "consulted", "advised", "recommended", "proposed",
    "audited", "reviewed", "inspected", "validated",
    "rolled-out", "rolled out", "deployed", "migrated", "integrated",
}


def score_content(
    cv_text: str,
    region: RegionProfile,
) -> Tuple[int, List[StructuralIssue]]:
    """Score content quality out of 15 points."""
    issues: List[StructuralIssue] = []

    # ---- A: bullet point density ----
    bullet_lines = _count_bullet_lines(cv_text)
    total_lines = len([l for l in cv_text.split("\n") if l.strip()])
    bullet_ratio = bullet_lines / total_lines if total_lines else 0

    if bullet_lines < 3:
        issues.append(StructuralIssue(
            severity="medium",
            type="too_few_bullets",
            description=(
                "Few or no bullet points detected. Both ATS systems and human "
                "recruiters scan for bullets — they're significantly more "
                "readable than paragraph-form descriptions of responsibilities."
            ),
            penalty=4,
        ))

    # ---- B: action verb usage ----
    verb_count = _count_action_verbs(cv_text)
    if verb_count < 3:
        issues.append(StructuralIssue(
            severity="medium",
            type="few_action_verbs",
            description=(
                "Fewer than 3 strong action verbs detected (led, managed, "
                "delivered, increased, etc.). Action-led bullets demonstrate "
                "ownership and outcomes; without them, CVs read as job descriptions "
                "rather than achievements."
            ),
            penalty=4,
        ))
    elif verb_count < 6:
        issues.append(StructuralIssue(
            severity="low",
            type="more_action_verbs_could_help",
            description=(
                f"Detected {verb_count} action verbs. Strong CVs typically lead "
                "8+ bullet points with action verbs to highlight achievements."
            ),
            penalty=2,
        ))

    # ---- C: quantified achievements ----
    # Numbers, percentages, currency amounts — anything that signals scale
    numeric_signals = _count_numeric_signals(cv_text, region)
    if numeric_signals == 0:
        issues.append(StructuralIssue(
            severity="medium",
            type="no_quantified_achievements",
            description=(
                "No quantified achievements detected (numbers, percentages, "
                "currency amounts, headcounts). Specifics like 'managed a R50M "
                "budget' or 'led a team of 12' significantly improve both ATS "
                "scoring and recruiter response."
            ),
            penalty=4,
        ))
    elif numeric_signals < 3:
        issues.append(StructuralIssue(
            severity="low",
            type="few_quantified_achievements",
            description=(
                f"Only {numeric_signals} quantified achievement(s) detected. "
                "Adding more specific numbers strengthens both ATS scoring and "
                "the impression of measurable impact."
            ),
            penalty=2,
        ))

    # ---- D: length sanity ----
    word_count = len(cv_text.split())
    expected_min = region.expected_length_pages[0] * 250  # ~250 words/page minimum
    expected_max = region.expected_length_pages[1] * 500  # ~500 words/page maximum

    if word_count < expected_min:
        issues.append(StructuralIssue(
            severity="medium",
            type="cv_too_short",
            description=(
                f"CV is approximately {word_count} words — short for the "
                f"{region.code} convention of {region.expected_length_pages[0]}-"
                f"{region.expected_length_pages[1]} pages. Recruiters often "
                "interpret very short CVs as lack of depth or experience."
            ),
            penalty=3,
        ))
    elif word_count > expected_max * 1.5:
        issues.append(StructuralIssue(
            severity="low",
            type="cv_too_long",
            description=(
                f"CV is approximately {word_count} words — long for the "
                f"{region.code} convention. Tighter editing usually improves "
                "both ATS keyword density and recruiter attention."
            ),
            penalty=2,
        ))

    # ---- E: first-person pronouns ----
    # CVs conventionally drop "I" and "my" — a sentence like "Led a team..."
    # is more standard than "I led a team..."
    first_person_count = len(re.findall(r"\b(I|my|me|myself)\b", cv_text))
    if first_person_count >= 5:
        issues.append(StructuralIssue(
            severity="low",
            type="overuse_of_first_person",
            description=(
                f"Detected {first_person_count} uses of 'I' / 'my' / 'me'. "
                "CVs conventionally drop the personal pronoun — start bullets "
                "with the action verb directly ('Led 12 staff' rather than "
                "'I led 12 staff')."
            ),
            penalty=1,
        ))

    # ---- Final score ----
    total_penalty = sum(issue.penalty for issue in issues)
    score = max(15 - total_penalty, 0)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda i: severity_order.get(i.severity, 9))

    return score, issues


# ---------- Internal helpers ----------

def _count_bullet_lines(cv_text: str) -> int:
    """Count lines that start with a bullet marker (•, -, *, ▪, etc.)."""
    bullet_pattern = re.compile(
        r"^\s*[\u2022\u25CF\u25AA\u25A0\u2023\u2043\-\*\u00B7]\s+",
        re.MULTILINE,
    )
    return len(bullet_pattern.findall(cv_text))


def _count_action_verbs(cv_text: str) -> int:
    """Count strong action verbs near the start of lines (most-likely-bullet position)."""
    count = 0
    for line in cv_text.split("\n"):
        line_clean = re.sub(r"^\s*[\u2022\u25CF\u25AA\u25A0\u2023\u2043\-\*\u00B7]\s+", "", line)
        line_clean = line_clean.strip()
        if not line_clean:
            continue
        first_word_match = re.match(r"^([A-Za-z\-]+)", line_clean)
        if first_word_match:
            first_word = first_word_match.group(1).lower()
            if first_word in ACTION_VERBS:
                count += 1
    return count


def _count_numeric_signals(cv_text: str, region: RegionProfile) -> int:
    """Count occurrences of numbers that suggest quantified achievements."""
    count = 0

    # Percentages
    count += len(re.findall(r"\b\d+(?:\.\d+)?%", cv_text))

    # Currency — region-aware
    if region.code == "ZA":
        count += len(re.findall(r"\bR\s?\d", cv_text))
        count += len(re.findall(r"\bZAR\s?\d", cv_text))
    elif region.code == "UK":
        count += len(re.findall(r"£\s?\d", cv_text))
        count += len(re.findall(r"\bGBP\s?\d", cv_text))
    elif region.code == "US":
        count += len(re.findall(r"\$\s?\d", cv_text))
        count += len(re.findall(r"\bUSD\s?\d", cv_text))

    # Standalone numbers in achievement-like contexts
    # ("led 12 people", "managed 250 accounts", "saved 30 hours")
    # Excluding 4-digit years (handled separately under structure)
    numbers = re.findall(r"(?<!\d)\d{1,3}(?:,\d{3})*(?!\d)", cv_text)
    # Filter out years
    non_year_numbers = [n for n in numbers if not (1900 <= int(n.replace(",", "")) <= 2100)]
    count += min(len(non_year_numbers), 10)  # Cap so a phone number doesn't run away with the count

    return count
