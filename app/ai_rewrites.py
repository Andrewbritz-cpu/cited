"""
AI-powered bullet point improvement suggestions.

Extracts bullet-like lines from the CV text, identifies which ones are
weakest (no action verb, no quantification, too vague), and generates
specific rewrite suggestions using pattern-based templates.

This is the core value differentiator of the R99 Tier 2 report. Free-tier
users see their score + top 3 issues. Paid users see their actual bullets
with specific, personalised improvement suggestions — the thing that makes
someone say "this was worth R99."

Future upgrade: call Claude API for truly contextual rewrites. Current
implementation uses pattern-matching + templates which is still far more
useful than generic advice.
"""

import re
from typing import List, Tuple
from dataclasses import dataclass

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
    "deployed", "migrated", "integrated",
}

WEAK_VERBS = {
    "responsible", "helped", "assisted", "participated", "involved",
    "worked", "did", "made", "got", "was", "had", "used", "handled",
    "dealt", "supported", "contributed", "served",
}

# Strong verb suggestions grouped by intent
VERB_UPGRADES = {
    "responsible": "Led", "helped": "Enabled", "assisted": "Led",
    "participated": "Contributed to", "involved": "Drove",
    "worked": "Drove", "did": "Delivered", "made": "Produced",
    "got": "Secured", "was": "Led", "had": "Managed",
    "used": "Leveraged", "handled": "Managed", "dealt": "Resolved",
    "supported": "Facilitated", "contributed": "Drove", "served": "Operated as",
}


@dataclass
class BulletRewrite:
    """A single bullet from the CV with improvement suggestions."""
    original: str
    issues: List[str]           # What's wrong: "no_action_verb", "no_numbers", "too_vague"
    suggestion: str             # The rewritten version
    improvement_note: str       # Why this is better


def extract_and_rewrite_bullets(cv_text: str, max_rewrites: int = 5) -> List[BulletRewrite]:
    """
    Extract bullet-like lines from the CV, score each one, and generate
    improvement suggestions for the weakest ones.

    Returns up to `max_rewrites` bullets, sorted worst-first.
    """
    bullets = _extract_bullets(cv_text)
    if not bullets:
        return []

    scored = [(b, _score_bullet(b)) for b in bullets]
    # Sort by score ascending (worst first), take the weakest
    scored.sort(key=lambda x: x[1][0])

    rewrites = []
    for bullet, (score, issues) in scored:
        if score >= 8 or not issues:
            continue  # Already decent
        suggestion, note = _generate_suggestion(bullet, issues)
        rewrites.append(BulletRewrite(
            original=bullet.strip(),
            issues=issues,
            suggestion=suggestion,
            improvement_note=note,
        ))
        if len(rewrites) >= max_rewrites:
            break

    return rewrites


def _extract_bullets(cv_text: str) -> List[str]:
    """Extract lines that look like bullet points or role descriptions."""
    bullets = []
    lines = cv_text.split("\n")

    for line in lines:
        clean = line.strip()
        if not clean or len(clean) < 15:
            continue

        # Skip section headers, names, dates, contact info
        if re.match(r"^(EXPERIENCE|EDUCATION|SKILLS|SUMMARY|PROFILE|CONTACT|REFERENCES)", clean, re.I):
            continue
        if re.match(r"^\d{4}\s*[-–—]", clean):
            continue
        if "@" in clean and "." in clean and len(clean) < 60:
            continue
        if re.match(r"^\+?\d[\d\s\-]{7,}", clean):
            continue

        # Bullet markers or lines that start with action-like words
        is_bullet = bool(re.match(r"^\s*[\u2022\u25CF\u25AA\u25A0\u2023\u2043\-\*\u00B7]\s+", line))
        starts_with_verb = False
        first_word = re.match(r"^[\u2022\u25CF\u25AA\-\*\u00B7\s]*([A-Za-z]+)", clean)
        if first_word:
            fw = first_word.group(1).lower()
            starts_with_verb = fw in ACTION_VERBS or fw in WEAK_VERBS

        # Include if it looks like a bullet or a responsibility description
        if is_bullet or starts_with_verb or (len(clean) > 30 and not clean.isupper()):
            # Skip very short items that are probably job titles or company names
            word_count = len(clean.split())
            if word_count >= 4:
                bullets.append(clean)

    return bullets


def _score_bullet(bullet: str) -> Tuple[int, List[str]]:
    """
    Score a bullet 0-10 (higher = better). Returns (score, list_of_issues).
    """
    score = 5  # Start neutral
    issues = []

    # Strip bullet marker for analysis
    clean = re.sub(r"^[\u2022\u25CF\u25AA\u25A0\u2023\u2043\-\*\u00B7\s]+", "", bullet).strip()

    # Check for action verb at start
    first_word = ""
    first_match = re.match(r"^([A-Za-z]+)", clean)
    if first_match:
        first_word = first_match.group(1).lower()

    if first_word in ACTION_VERBS:
        score += 2
    elif first_word in WEAK_VERBS:
        score -= 2
        issues.append("weak_verb")
    elif first_word in ("i", "my", "the", "a", "an"):
        score -= 1
        issues.append("starts_with_pronoun")
    else:
        # Doesn't start with any verb — might be a noun phrase
        if not any(v in clean.lower().split()[:3] for v in ACTION_VERBS):
            issues.append("no_action_verb")
            score -= 1

    # Check for numbers/quantification
    has_numbers = bool(re.search(r"\d+", clean))
    has_percent = bool(re.search(r"\d+%", clean))
    has_currency = bool(re.search(r"[R£$]\s?\d|ZAR|GBP|USD", clean))

    if has_percent or has_currency:
        score += 2
    elif has_numbers:
        score += 1
    else:
        issues.append("no_numbers")
        score -= 1

    # Check for vagueness
    vague_phrases = [
        "responsible for", "duties included", "helped with",
        "assisted in", "involved in", "worked on",
        "various", "multiple", "several", "etc",
    ]
    for phrase in vague_phrases:
        if phrase in clean.lower():
            issues.append("too_vague")
            score -= 1
            break

    # Check length — too short is weak, too long is unfocused
    words = len(clean.split())
    if words < 6:
        issues.append("too_short")
        score -= 1
    elif words > 35:
        issues.append("too_long")
        score -= 1

    return max(0, min(10, score)), issues


def _generate_suggestion(bullet: str, issues: List[str]) -> Tuple[str, str]:
    """
    Generate a specific rewrite suggestion based on the identified issues.
    Returns (suggested_rewrite, explanation_note).
    """
    clean = re.sub(r"^[\u2022\u25CF\u25AA\u25A0\u2023\u2043\-\*\u00B7\s]+", "", bullet).strip()

    # Identify the first word
    first_match = re.match(r"^([A-Za-z]+)", clean)
    first_word = first_match.group(1).lower() if first_match else ""
    rest = clean[len(first_word):].strip() if first_word else clean

    parts = []
    notes = []

    # Fix weak verb
    if "weak_verb" in issues and first_word in VERB_UPGRADES:
        new_verb = VERB_UPGRADES[first_word]
        # Strip filler phrases between the weak verb and the actual content
        cleaned_rest = rest
        filler_patterns = [
            r"^(for|in|on|with)\s+",
            r"^(responsible\s+for|involved\s+in|involved\s+with)\s+",
        ]
        for pat in filler_patterns:
            cleaned_rest = re.sub(pat, "", cleaned_rest, flags=re.I).strip()
        suggestion_start = f"{new_verb} {cleaned_rest}"
        parts.append(suggestion_start)
        notes.append(f"Replaced '{first_word}' with '{new_verb}' — stronger action verb signals ownership")
    elif "no_action_verb" in issues or "starts_with_pronoun" in issues:
        # Remove pronoun if present
        no_pronoun = re.sub(r"^(I|My|We|Our)\s+", "", clean, flags=re.I)
        # Try to find a verb already in the sentence to promote
        words = no_pronoun.split()
        promoted = False
        for i, w in enumerate(words[:5]):
            if w.lower().rstrip(".,;:") in ACTION_VERBS:
                # Promote this verb to the front
                verb = w[0].upper() + w[1:]
                remaining = " ".join(words[:i] + words[i+1:])
                parts.append(f"{verb} {remaining}")
                notes.append(f"Moved '{w}' to the front — lead with the action verb")
                promoted = True
                break
        if not promoted:
            parts.append(f"Led {no_pronoun.lower()}" if not no_pronoun[0].isupper() else f"Delivered {no_pronoun}")
            notes.append("Added action verb at the start — bullets should lead with what you did")
    else:
        parts.append(clean)

    current = parts[-1] if parts else clean

    # Add quantification prompt
    if "no_numbers" in issues:
        current += " [add: specific number, %, or R amount]"
        notes.append("Add a number — 'managed projects' becomes 'managed 8 projects saving R2M annually'")

    # Fix vagueness
    if "too_vague" in issues:
        # Remove vague phrases
        for phrase in ["responsible for", "duties included", "helped with", "assisted in", "involved in", "worked on"]:
            if phrase in current.lower():
                idx = current.lower().index(phrase)
                current = current[:idx] + current[idx + len(phrase):]
                current = current.strip().strip(",").strip()
        notes.append("Removed vague language — be specific about what YOU did, not what the role required")

    if "too_long" in issues:
        notes.append("Consider splitting into two bullets — each should convey one achievement")

    if "too_short" in issues:
        notes.append("Expand with context and impact — what was the result?")

    suggestion = current.strip()
    # Capitalise first letter
    if suggestion and suggestion[0].islower():
        suggestion = suggestion[0].upper() + suggestion[1:]

    note = ". ".join(notes) if notes else "Minor improvements to strengthen impact."

    return suggestion, note
