"""Phase 3.3 — pydantic v2 schema for Recommendations.

A Recommendation is a structured suggestion to the user with a
proposed_params dict the existing render flow can consume. The
recommender NEVER calls start_render directly — it returns
Recommendations; the user clicks Confirm in a dialog; THEN
auto_render queues the re-render.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# Bump on incompatible schema change.
OPT_SCHEMA_VERSION = 1


class RecommendationKind(str, Enum):
    """Categorical kind. UI groups recommendations by kind."""

    RAISE_QUALITY = "raise_quality"
    LOWER_QUALITY = "lower_quality"
    INCREASE_DIFFERENCE = "increase_difference"
    DECREASE_DIFFERENCE = "decrease_difference"
    USE_GPU = "use_gpu"
    USE_CPU = "use_cpu"
    RETRY_AS_IS = "retry_as_is"
    SWITCH_ENCODER = "switch_encoder"
    DEBUG_LOG = "debug_log"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    """How confident the heuristic is. UI surfaces this verbatim."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Recommendation(BaseModel):
    """Single structured suggestion.

    Fields:
        kind                  enum classifier
        reason                one-sentence human reason
        confidence            HIGH / MEDIUM / LOW
        delta_summary         short diff vs original (display)
        proposed_params       dict the caller plugs into the
                              render flow. Keys are advisory and
                              optional; current consumers look
                              for: encoder_id (str), crf_delta
                              (int), preset_family (str),
                              gpu_enabled (bool), max_quality
                              (bool), extra_vf (list[str]).
        original_preset_ids   list of preset IDs that produced
                              the render this recommendation
                              targets.
        target_output_basename  basename suggestion (e.g.
                                "clip01_h264_v2.mp4"); None means
                                "let naming_utils handle it".
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=OPT_SCHEMA_VERSION)
    kind: RecommendationKind
    reason: str
    confidence: Confidence
    delta_summary: str = ""
    proposed_params: dict[str, Any] = Field(default_factory=dict)
    original_preset_ids: list[str] = Field(default_factory=list)
    target_output_basename: Optional[str] = None


__all__ = [
    "OPT_SCHEMA_VERSION",
    "Confidence",
    "Recommendation",
    "RecommendationKind",
]
