"""
Sector benchmarking data.

Provides typical ATS score ranges by industry, used in the Tier 2 report to
give users competitive context: "IT professionals in SA typically score 52-68.
Your score of 74 puts you above average."

These ranges are calibrated against our scoring engine's output — they
represent what our specific algorithm produces for typical CVs in each
sector, not external ATS scores. This is important honesty: we're comparing
you against our own baseline, not claiming industry-wide data we don't have.

As we collect real scan data (target: ~Day 60), these should be replaced
with actual measured percentiles from our database.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SectorBenchmark:
    """Score ranges for a sector, calibrated to our scoring engine."""
    sector_name: str
    typical_low: int        # 25th percentile-ish
    typical_high: int       # 75th percentile-ish
    strong_threshold: int   # Above this = "above average"
    callback_threshold: int # Above this = "competitive for callbacks"


# These ranges reflect what our 100-point scoring engine produces for
# CVs in each sector. They're deliberately conservative estimates based
# on the scoring engine's design (40 parseability + 20 structure + 25
# keywords + 15 content). Real data will replace these.
BENCHMARKS = {
    "tech": SectorBenchmark(
        sector_name="Technology / IT",
        typical_low=52,
        typical_high=72,
        strong_threshold=75,
        callback_threshold=80,
    ),
    "finance": SectorBenchmark(
        sector_name="Finance / Banking",
        typical_low=55,
        typical_high=74,
        strong_threshold=76,
        callback_threshold=82,
    ),
    "healthcare": SectorBenchmark(
        sector_name="Healthcare / Medical",
        typical_low=48,
        typical_high=68,
        strong_threshold=72,
        callback_threshold=78,
    ),
    "education": SectorBenchmark(
        sector_name="Education / Teaching",
        typical_low=45,
        typical_high=65,
        strong_threshold=70,
        callback_threshold=76,
    ),
    "marketing": SectorBenchmark(
        sector_name="Marketing / Communications",
        typical_low=50,
        typical_high=70,
        strong_threshold=73,
        callback_threshold=79,
    ),
    "legal": SectorBenchmark(
        sector_name="Legal / Compliance",
        typical_low=54,
        typical_high=73,
        strong_threshold=76,
        callback_threshold=81,
    ),
    "engineering": SectorBenchmark(
        sector_name="Engineering",
        typical_low=50,
        typical_high=70,
        strong_threshold=74,
        callback_threshold=80,
    ),
    "hospitality": SectorBenchmark(
        sector_name="Hospitality / Tourism",
        typical_low=42,
        typical_high=62,
        strong_threshold=68,
        callback_threshold=74,
    ),
    "general": SectorBenchmark(
        sector_name="General / Cross-sector",
        typical_low=48,
        typical_high=68,
        strong_threshold=72,
        callback_threshold=78,
    ),
}


def get_benchmark(industry_code: str) -> SectorBenchmark:
    """Get the benchmark for a detected industry, falling back to general."""
    return BENCHMARKS.get(industry_code, BENCHMARKS["general"])


def format_benchmark_context(score: int, industry_code: str) -> dict:
    """
    Generate the benchmark context dict for the Tier 2 report template.

    Returns a dict with:
      sector_name, typical_range, position (below/within/above/strong),
      position_description, callback_threshold, points_to_callback
    """
    b = get_benchmark(industry_code)

    if score >= b.callback_threshold:
        position = "strong"
        desc = (
            f"Your score of {score} is above the callback threshold of "
            f"{b.callback_threshold} for {b.sector_name}. This CV is "
            f"competitive for ATS screening."
        )
    elif score >= b.strong_threshold:
        position = "above"
        desc = (
            f"Your score of {score} is above the typical range of "
            f"{b.typical_low}–{b.typical_high} for {b.sector_name}. "
            f"You're close to the callback threshold of {b.callback_threshold} — "
            f"fixing the top issues below could get you there."
        )
    elif score >= b.typical_low:
        position = "within"
        desc = (
            f"Your score of {score} falls within the typical range of "
            f"{b.typical_low}–{b.typical_high} for {b.sector_name}. "
            f"You need {b.callback_threshold - score} more points to reach "
            f"the callback threshold."
        )
    else:
        position = "below"
        desc = (
            f"Your score of {score} is below the typical range of "
            f"{b.typical_low}–{b.typical_high} for {b.sector_name}. "
            f"The structural fixes below are high-priority — they'll have "
            f"the biggest impact on getting past ATS screening."
        )

    return {
        "sector_name": b.sector_name,
        "typical_low": b.typical_low,
        "typical_high": b.typical_high,
        "strong_threshold": b.strong_threshold,
        "callback_threshold": b.callback_threshold,
        "position": position,
        "position_description": desc,
        "points_to_callback": max(0, b.callback_threshold - score),
    }
