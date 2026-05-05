"""
Industry detection and per-industry keyword baselines.

When the user doesn't paste a job description, we still need *something* to
score keyword fit against. This module infers the industry from the CV itself
(or from the job ad if provided) and supplies a curated keyword list to score
against.

The industry list is deliberately broad rather than deep — we cover the
biggest SA mid-market hiring categories rather than trying to be everything.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Industry:
    code: str
    name: str
    detection_signals: List[str]   # Words that suggest this industry
    core_keywords: List[str]        # Keywords a strong CV in this industry contains
    weight: int = 1                 # Tiebreaker — higher wins on equal hits


INDUSTRIES: Dict[str, Industry] = {
    "tech": Industry(
        code="tech",
        name="Technology / IT",
        detection_signals=[
            "software", "developer", "engineer", "programming", "code",
            "devops", "cloud", "agile", "scrum", "git", "ci/cd",
            "kubernetes", "docker", "aws", "azure", "gcp", "linux",
            "javascript", "python", "java", "typescript", "sql",
            "api", "microservices", "infrastructure", "frontend",
            "backend", "fullstack",
        ],
        core_keywords=[
            "agile methodology", "version control", "ci/cd pipelines",
            "cloud infrastructure", "microservices architecture",
            "API integration", "stakeholder management",
            "technical leadership", "code review", "system design",
        ],
        weight=2,
    ),

    "finance": Industry(
        code="finance",
        name="Finance / Accounting",
        detection_signals=[
            "accountant", "accounting", "audit", "tax", "ifrs", "gaap",
            "financial reporting", "saica", "saipa", "cpa", "cima",
            "treasury", "investment", "portfolio", "compliance",
            "reconciliation", "ledger", "balance sheet", "income statement",
            "p&l", "forecasting", "budgeting", "fp&a",
        ],
        core_keywords=[
            "financial reporting", "regulatory compliance", "IFRS",
            "audit experience", "stakeholder reporting",
            "budget management", "variance analysis",
            "internal controls", "risk management",
        ],
    ),

    "marketing": Industry(
        code="marketing",
        name="Marketing / Communications",
        detection_signals=[
            "marketing", "brand", "campaign", "social media", "content",
            "seo", "sem", "ppc", "google ads", "facebook ads", "linkedin ads",
            "copywriter", "content strategy", "digital marketing",
            "growth", "conversion", "ctr", "engagement",
            "email marketing", "newsletter",
        ],
        core_keywords=[
            "campaign management", "ROI measurement", "content strategy",
            "brand positioning", "stakeholder engagement",
            "performance marketing", "audience segmentation",
            "creative direction", "marketing analytics",
        ],
    ),

    "sales": Industry(
        code="sales",
        name="Sales / Business Development",
        detection_signals=[
            "sales", "business development", "account manager",
            "key accounts", "quota", "pipeline", "crm", "salesforce",
            "hubspot", "lead generation", "cold calling",
            "negotiation", "closing", "b2b", "b2c",
        ],
        core_keywords=[
            "pipeline management", "stakeholder negotiation",
            "revenue growth", "key account management",
            "CRM proficiency", "sales forecasting",
            "client retention", "consultative selling",
        ],
    ),

    "operations": Industry(
        code="operations",
        name="Operations / Logistics",
        detection_signals=[
            "operations", "logistics", "supply chain", "procurement",
            "warehouse", "inventory", "production", "manufacturing",
            "lean", "six sigma", "process improvement", "qa",
            "quality", "iso", "vendor management",
        ],
        core_keywords=[
            "process optimisation", "supply chain management",
            "vendor management", "operational efficiency",
            "stakeholder coordination", "continuous improvement",
            "compliance management", "team leadership",
        ],
    ),

    "hr": Industry(
        code="hr",
        name="Human Resources",
        detection_signals=[
            "human resources", "hr ", "talent", "recruitment",
            "recruiter", "people operations", "onboarding",
            "employee relations", "payroll", "compensation",
            "benefits", "training", "learning and development",
            "l&d", "ld ", "performance management",
        ],
        core_keywords=[
            "talent acquisition", "employee engagement",
            "performance management", "stakeholder management",
            "policy development", "L&D programmes",
            "compensation strategy", "labour law compliance",
        ],
    ),

    "education": Industry(
        code="education",
        name="Education / Training",
        detection_signals=[
            "teacher", "lecturer", "tutor", "education", "school",
            "university", "curriculum", "lesson", "classroom",
            "pedagogy", "caps", "sace", "academic",
            "research", "facilitator",
        ],
        core_keywords=[
            "curriculum development", "classroom management",
            "student engagement", "differentiated instruction",
            "assessment design", "stakeholder communication",
            "educational technology",
        ],
    ),

    "healthcare": Industry(
        code="healthcare",
        name="Healthcare / Medical",
        detection_signals=[
            "doctor", "nurse", "medical", "clinical", "patient",
            "hospital", "clinic", "hpcsa", "pharmacy", "pharmacist",
            "physiotherapy", "occupational therapy", "radiography",
            "healthcare", "diagnosis", "treatment",
        ],
        core_keywords=[
            "patient care", "clinical assessment", "treatment planning",
            "regulatory compliance", "multidisciplinary collaboration",
            "evidence-based practice", "clinical documentation",
        ],
    ),

    "legal": Industry(
        code="legal",
        name="Legal",
        detection_signals=[
            "attorney", "advocate", "lawyer", "legal", "litigation",
            "contract", "compliance", "paralegal", "court",
            "law firm", "lpc", "llb", "lsc",
        ],
        core_keywords=[
            "contract drafting", "regulatory compliance", "litigation",
            "legal research", "stakeholder advisory",
            "due diligence", "case management",
        ],
    ),

    "general": Industry(
        code="general",
        name="General / Cross-functional",
        detection_signals=[],  # Default fallback
        core_keywords=[
            "stakeholder management", "project management",
            "team leadership", "strategic planning",
            "process improvement", "performance reporting",
            "cross-functional collaboration", "problem solving",
        ],
    ),
}


def detect_industry(haystack: str) -> Industry:
    """
    Score each industry by how many of its detection signals appear in the
    text. Returns the winning industry, or 'general' if no industry has a
    meaningful lead.
    """
    haystack = haystack.lower()
    scores = {}
    for code, industry in INDUSTRIES.items():
        if not industry.detection_signals:
            continue
        hits = sum(1 for sig in industry.detection_signals if sig in haystack)
        scores[code] = hits * industry.weight

    if not scores or max(scores.values()) < 2:
        return INDUSTRIES["general"]

    best_code = max(scores, key=scores.get)
    return INDUSTRIES[best_code]
