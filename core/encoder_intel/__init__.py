"""Phase 3.5 — encoder intelligence layer (local-only).

Reads the user's local ffmpeg / pynvml / GPU. Produces capability
matrices, preset compatibility verdicts, and fallback plans. All
advisory: no forced switching, no hidden preset mutation, no
RenderWorker change.
"""

from __future__ import annotations

from core.encoder_intel.analyzer import (
    CompatibilityVerdict,
    PresetClassification,
    Severity,
    classify_preset,
    compatibility_check,
    nvenc_session_budget,
)
from core.encoder_intel.fallback import FallbackPlan, plan_fallback
from core.encoder_intel.models import INTEL_SCHEMA_VERSION

__all__ = [
    "INTEL_SCHEMA_VERSION",
    "CompatibilityVerdict",
    "FallbackPlan",
    "PresetClassification",
    "Severity",
    "classify_preset",
    "compatibility_check",
    "nvenc_session_budget",
    "plan_fallback",
]
