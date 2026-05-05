"""
Backwards-compatible shim.

Historical entry point — kept so that any code importing `from app.scorer
import score_cv` continues to work. The real implementation now lives in
`app/scoring/`.
"""

from app.scoring import score_cv, ScoringResult

__all__ = ["score_cv", "ScoringResult"]
