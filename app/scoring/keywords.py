"""
Keyword fit scoring (25% of total score).

Two paths:
1. If the user provided a job ad — extract its key terms and score the CV
   against them (this is the standard ATS use case).
2. If they didn't — detect the industry from the CV itself and score against
   that industry's baseline keyword list.

Heuristic-only: no LLM calls. Keyword extraction from the job ad uses
frequency analysis with stopword filtering. It's not as good as an LLM, but
for v1 it gives us a defensible signal at zero API cost.
"""

import re
from collections import Counter
from typing import List, Tuple

from app.scoring.industry import detect_industry, Industry


# Words and phrases that show up in every job ad and shouldn't count as "keywords"
STOPWORDS = {
    # Generic English stopwords
    "the", "and", "for", "you", "with", "are", "have", "this", "that",
    "from", "will", "your", "our", "able", "about", "after", "all",
    "also", "any", "been", "before", "being", "between", "but", "can",
    "could", "did", "does", "each", "few", "had", "has", "having",
    "here", "how", "if", "in", "into", "is", "it", "its", "may",
    "more", "most", "must", "not", "of", "on", "or", "other",
    "should", "so", "some", "such", "than", "then", "there", "these",
    "they", "those", "through", "to", "up", "was", "were", "what",
    "when", "where", "which", "while", "who", "why", "would",

    # Job-ad boilerplate
    "experience", "experienced", "ability", "able", "candidate",
    "candidates", "company", "team", "role", "position", "include",
    "including", "responsibilities", "requirements", "preferred",
    "essential", "manage", "managing", "ensure", "ensuring",
    "looking", "seeking", "join", "work", "working", "hiring",
    "year", "years", "months", "month", "salary", "benefits",
    "offer", "offers", "opportunity", "opportunities",
    "skills", "skill", "knowledge", "understanding", "familiar",
    "familiarity", "good", "great", "excellent", "strong",
    "across", "within", "throughout", "during",
    "level", "junior", "senior", "lead", "head",
    "must", "should", "will", "shall",
    "applicants", "applicant", "applicable", "apply", "application",
    "needed", "wanted", "required", "needed", "ideally",
    "successful", "track", "record", "proven", "demonstrated",
    "growing", "established", "leading", "leader",
    "based", "primary", "secondary", "successful",
    "individual", "person", "professional",
    "duties", "tasks", "deliverables",
}


def score_keywords(
    cv_text: str,
    job_description: str,
) -> Tuple[int, List[str], List[str], str]:
    """
    Score keyword fit out of 25 points.

    Returns:
        (score, missing_keywords, matched_keywords, source_description)
        - source_description identifies whether keywords came from a job ad
          or from an industry baseline. Useful for the result panel UI.
    """
    cv_lower = cv_text.lower()

    if job_description and len(job_description.strip()) >= 100:
        keywords = _extract_keywords_from_job_ad(job_description)
        source_description = "your job description"
    else:
        industry = detect_industry(cv_lower)
        keywords = list(industry.core_keywords)
        source_description = f"the {industry.name.lower()} baseline"

    if not keywords:
        # Nothing to score against — give them the benefit of the doubt
        return 18, [], [], "no clear keyword source"

    matched, missing = _split_keywords_by_match(keywords, cv_lower)

    # Score: how many of the keyword set we matched
    match_ratio = len(matched) / len(keywords) if keywords else 0
    score = round(match_ratio * 25)

    # Cap missing list at 15 for output (we'll trim further in the route handler)
    missing = missing[:15]
    matched = matched[:15]

    return score, missing, matched, source_description


# ---------- Internal helpers ----------

def _extract_keywords_from_job_ad(job_ad: str) -> List[str]:
    """
    Extract candidate keywords from a job ad using:
    - bigram and unigram frequency
    - section-aware weighting (terms in 'Requirements' or 'Skills' sections
      get higher weight)
    - stopword filtering
    - capitalisation as a signal (proper nouns and acronyms matter more)
    """
    job_lower = job_ad.lower()

    # Find boundaries of common section markers and weight content inside them
    weighted_chunks = _split_and_weight_sections(job_ad)

    # Tokenise + score
    counter: Counter = Counter()

    for chunk_text, weight in weighted_chunks:
        # Bigrams (two-word phrases) carry more meaning than single words
        for bigram in _extract_bigrams(chunk_text):
            counter[bigram] += weight * 2

        # Unigrams — but only the substantive ones
        for word in _extract_substantive_words(chunk_text):
            counter[word] += weight

    # Acronyms (3-5 capital letters) deserve a bonus; ATS systems treat them
    # as exact-match tokens
    for acronym in re.findall(r"\b[A-Z]{2,5}\b", job_ad):
        if acronym.lower() not in STOPWORDS and len(acronym) >= 2:
            counter[acronym] += 4

    # Take the top 12 candidate keywords by score
    top_candidates = [term for term, _ in counter.most_common(20)]

    # Light deduplication — drop unigrams that appear inside our chosen bigrams
    deduped = _dedupe_overlapping_keywords(top_candidates)
    return deduped[:12]


def _split_and_weight_sections(job_ad: str) -> List[Tuple[str, int]]:
    """
    Slice the job ad by recognisable section markers and weight each section.
    Requirements/Responsibilities/Qualifications/Skills sections weight 3x;
    everything else weights 1x.
    """
    high_weight_markers = [
        "requirements", "qualifications", "skills required",
        "what you bring", "what you'll need", "you must have",
        "essential criteria", "key skills", "technical skills",
        "responsibilities", "what you'll do", "duties",
    ]

    lines = job_ad.split("\n")
    chunks: List[Tuple[str, int]] = []
    current_chunk: List[str] = []
    current_weight = 1

    for line in lines:
        line_lower = line.lower().strip()
        is_marker = any(m in line_lower for m in high_weight_markers)

        if is_marker and current_chunk:
            # Flush previous chunk
            chunks.append(("\n".join(current_chunk), current_weight))
            current_chunk = []
            current_weight = 3
        elif is_marker:
            current_weight = 3

        current_chunk.append(line)

    if current_chunk:
        chunks.append(("\n".join(current_chunk), current_weight))

    return chunks if chunks else [(job_ad, 1)]


def _extract_bigrams(text: str) -> List[str]:
    """Extract two-word phrases that look meaningful (no stopwords on either side).

    Uses sentence/clause-level segmentation: punctuation breaks the windowing,
    so "stakeholder management, cloud infrastructure" doesn't produce the
    spurious bigram "management cloud".
    """
    bigrams: List[str] = []

    # Split on punctuation that signals end of a clause/list-item
    clauses = re.split(r"[,.;:!?\n\(\)\[\]\-]+", text)

    for clause in clauses:
        words = re.findall(r"\b[A-Za-z][A-Za-z\-]{2,}\b", clause)
        for i in range(len(words) - 1):
            a, b = words[i].lower(), words[i + 1].lower()
            if a in STOPWORDS or b in STOPWORDS:
                continue
            if len(a) < 4 or len(b) < 4:
                continue
            bigrams.append(f"{words[i]} {words[i + 1]}".lower())

    return bigrams


def _extract_substantive_words(text: str) -> List[str]:
    """Single words that aren't in the stopword list and are long enough."""
    words = re.findall(r"\b[A-Za-z][A-Za-z\-]{4,}\b", text)
    return [
        w.lower() for w in words
        if w.lower() not in STOPWORDS and len(w) >= 5
    ]


def _dedupe_overlapping_keywords(candidates: List[str]) -> List[str]:
    """
    If we have both 'project management' (bigram) and 'project' (unigram)
    in the candidate list, keep only the bigram — it's more specific.
    """
    bigrams = [c for c in candidates if " " in c]
    bigram_words = set()
    for bigram in bigrams:
        bigram_words.update(bigram.split())

    result = []
    for candidate in candidates:
        if " " in candidate:
            result.append(candidate)
        elif candidate not in bigram_words:
            result.append(candidate)

    return result


def _split_keywords_by_match(
    keywords: List[str],
    cv_lower: str,
) -> Tuple[List[str], List[str]]:
    """Return (matched, missing) given a keyword list and lowercased CV text."""
    matched, missing = [], []
    for keyword in keywords:
        kw_lower = keyword.lower()
        # For multi-word keywords, accept the phrase OR all its words appearing
        # within a reasonable window
        if " " in kw_lower:
            if kw_lower in cv_lower or _all_words_present(kw_lower, cv_lower):
                matched.append(keyword)
            else:
                missing.append(keyword)
        else:
            if _word_boundary_match(kw_lower, cv_lower):
                matched.append(keyword)
            else:
                missing.append(keyword)
    return matched, missing


def _word_boundary_match(word: str, haystack: str) -> bool:
    """
    Match a word with word boundaries. This avoids the 'IT' inside 'with'
    substring problem that the project memory specifically calls out.
    """
    pattern = r"\b" + re.escape(word) + r"\b"
    return bool(re.search(pattern, haystack))


def _all_words_present(phrase: str, haystack: str) -> bool:
    """Loose match for multi-word keywords — all words present (not necessarily adjacent)."""
    return all(_word_boundary_match(word, haystack) for word in phrase.split())
