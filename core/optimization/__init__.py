"""Phase 3.3 — local-only optimization / recommendation layer.

Pure-Python heuristics over Phase 3.1 queue history + Phase 3.2
score data. No network. No remote service. No login. No
RenderWorker change. Every recommendation is advisory; the user
confirms each one via a dialog before any re-render fires. No
silent re-renders, no destructive overwrites, no auto-applied
preset switches.
"""

from __future__ import annotations

from core.optimization.batch_analyzer import BatchSummary, analyze_batch
from core.optimization.failure_classifier import classify_failure
from core.optimization.quality_classifier import Health, classify_health
from core.optimization.recommendation_models import (
    OPT_SCHEMA_VERSION,
    Confidence,
    Recommendation,
    RecommendationKind,
)
from core.optimization.recommender import recommend_for_render

__all__ = [
    "OPT_SCHEMA_VERSION",
    "BatchSummary",
    "Confidence",
    "Health",
    "Recommendation",
    "RecommendationKind",
    "analyze_batch",
    "classify_failure",
    "classify_health",
    "recommend_for_render",
]
