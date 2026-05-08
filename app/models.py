"""Pydantic models — the typed contract between scorer, API, and frontend."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Severity = Literal["low", "medium", "high", "critical"]
Region = Literal["ZA", "UK", "US"]


class StructuralIssue(BaseModel):
    """A specific ATS-breaking structural problem in a CV."""
    severity: Severity
    type: str = Field(..., description="Machine-readable issue type, e.g. 'multi_column_layout'")
    description: str = Field(..., description="Human-readable explanation for the user")
    penalty: int = Field(..., ge=0, le=100, description="Points deducted from the score")


class ScoringResult(BaseModel):
    """Full output of the scoring engine. Used internally — not all of it is
    returned to the free-tier API response."""
    score: int = Field(..., ge=0, le=100)
    region: Region
    rejection_estimate: int = Field(..., ge=0, le=100, description="Estimated % rejection rate")
    structural_issues: List[StructuralIssue]
    missing_keywords: List[str]
    score_breakdown: dict


class FreeScanResponse(BaseModel):
    """What the free-tier API returns to the frontend.

    Deliberately limited — full keyword lists, AI bullet rewrites, and
    sector benchmarking are gated behind the R99 Tier 2 upgrade.
    """
    scan_id: str
    score: int
    region: Region
    rejection_estimate: int
    structural_issues: List[StructuralIssue]  # capped at 3 by the route handler
    missing_keyword_count: int                # count only — actual list is Tier 2
    matched_keyword_count: int                # count only — actual list is Tier 2
    total_issue_count: int                    # total issues found (free shows 3)
    upgrade_url: str
