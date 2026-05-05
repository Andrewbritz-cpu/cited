"""
Regional profile data.

ZA / UK / US profiles each carry concrete differences:
- phone-number patterns, currency markers, location markers
- conventional terms ("CV" vs "Resume", "B-BBEE" vs "EEO")
- length/page expectations
- date-format preferences
- region-specific certifications and qualifications

The auto-detection function ranks signals across all three and picks the winner,
defaulting to ZA on ties (this is a SA-first product).
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class RegionProfile:
    code: str
    name: str

    # Phone-number regex patterns (compiled lazily by callers)
    phone_patterns: List[str]

    # Strong signals — multi-character markers that are nearly diagnostic
    strong_signals: List[str]

    # Weak signals — common terms that nudge detection
    weak_signals: List[str]

    # Conventional document terms
    document_term: str           # "CV" or "Résumé"
    expected_length_pages: tuple # (min, max) e.g. (1, 3)

    # Date format preference
    date_format_preference: str  # "DD/MM/YYYY" or "MM/DD/YYYY"
    date_format_examples: List[str]

    # Region-specific certifications/qualifications worth flagging if missing
    expected_certifications_or_bodies: List[str] = field(default_factory=list)


PROFILES: Dict[str, RegionProfile] = {
    "ZA": RegionProfile(
        code="ZA",
        name="South Africa",
        phone_patterns=[
            r"\+27\s?\(?0?\)?\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",
            r"\b0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b",
        ],
        strong_signals=[
            "south africa", "+27", "b-bbee", "bbbee", "saqa", "sace",
            "johannesburg", "cape town", "durban", "pretoria",
            "port elizabeth", "gqeberha", "stellenbosch", "bloemfontein",
            "kwazulu", "gauteng", "western cape", "mpumalanga", "limpopo",
            "vat number", "company registration", "id number",
        ],
        weak_signals=[
            "rand ", "zar", " r ", "sars", "uif", "rsa",
            "matric", "national senior certificate", "afrikaans",
            "isizulu", "isixhosa",
        ],
        document_term="CV",
        expected_length_pages=(2, 4),
        date_format_preference="DD/MM/YYYY",
        date_format_examples=["15/03/2024", "March 2024", "Mar 2024"],
        expected_certifications_or_bodies=[
            "SAICA", "SAIPA", "ECSA", "HPCSA", "SACAP", "SACE",
        ],
    ),

    "UK": RegionProfile(
        code="UK",
        name="United Kingdom",
        phone_patterns=[
            r"\+44\s?\(?0?\)?\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}",
            r"\b0\d{4}[\s\-]?\d{6}\b",
        ],
        strong_signals=[
            "united kingdom", "+44", "london", "manchester", "birmingham",
            "edinburgh", "glasgow", "leeds", "liverpool", "bristol",
            "ucas", "ofsted", "national insurance", "ni number",
            "england", "scotland", "wales",
        ],
        weak_signals=[
            "£", "gbp", "sterling", "pound", "ltd ", "plc",
            "a-level", "gcse", "btec",
        ],
        document_term="CV",
        expected_length_pages=(2, 3),
        date_format_preference="DD/MM/YYYY",
        date_format_examples=["15/03/2024", "March 2024", "Mar 2024"],
        expected_certifications_or_bodies=[
            "ACA", "ACCA", "CIMA", "CIPD", "RICS", "MRICS", "CharteredEng",
        ],
    ),

    "US": RegionProfile(
        code="US",
        name="United States",
        phone_patterns=[
            r"\+1\s?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
            r"\b\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}\b",
        ],
        strong_signals=[
            "united states", "usa ", "new york", "san francisco",
            "los angeles", "chicago", "boston", "seattle", "austin",
            "401k", "401(k)", "h1b", "h-1b", "social security",
        ],
        weak_signals=[
            "$", "usd", " llc", " inc.", " inc,", " corp",
            "résumé", "resume", "high school diploma", "ged",
            "associate's", "bachelor's", "master's",
        ],
        document_term="Résumé",
        expected_length_pages=(1, 2),
        date_format_preference="MM/DD/YYYY",
        date_format_examples=["03/15/2024", "March 2024", "Mar 2024"],
        expected_certifications_or_bodies=[
            "CPA", "PE", "PMP", "SHRM", "CFA",
        ],
    ),
}


def detect_region(haystack: str, explicit: str = "auto") -> RegionProfile:
    """
    Pick the most likely region from text content. Returns the profile object.

    Rules:
    - If the user explicitly chose ZA/UK/US, honour it.
    - Otherwise, score each profile by signal hits (strong = 3, weak = 1).
    - Default to ZA on ties or if nothing matches (this is a SA-first product).
    """
    if explicit and explicit.upper() in PROFILES:
        return PROFILES[explicit.upper()]

    haystack = haystack.lower()
    scores = {}
    for code, profile in PROFILES.items():
        score = 0
        for signal in profile.strong_signals:
            if signal in haystack:
                score += 3
        for signal in profile.weak_signals:
            if signal in haystack:
                score += 1
        scores[code] = score

    # Pick the winner; ties go to ZA per product positioning
    best_code = max(scores, key=lambda c: (scores[c], c == "ZA"))
    return PROFILES[best_code]
