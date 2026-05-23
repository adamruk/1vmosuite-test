"""Phase 3.5 — fallback planner.

Pure function. Given a CompatibilityVerdict + the available GPU
capability surface, returns a ranked list of codec alternatives.
The user reviews and confirms via the Phase 3.3
RecommendationDialog — Phase 3.5 never auto-applies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FallbackStep:
    codec: str
    reason: str
    confidence: str = "medium"


@dataclass
class FallbackPlan:
    """Ranked alternatives, best-first."""

    steps: List[FallbackStep] = field(default_factory=list)
    note: str = ""

    def is_empty(self) -> bool:
        return not self.steps

    def primary(self) -> Optional[FallbackStep]:
        return self.steps[0] if self.steps else None


def _caps_view(gpu_caps):
    return {
        "h264_available": getattr(gpu_caps, "h264_available", True)
        if gpu_caps
        else True,
        "hevc_available": getattr(gpu_caps, "hevc_available", True)
        if gpu_caps
        else True,
        "av1_available": getattr(gpu_caps, "av1_available", True) if gpu_caps else True,
        "gpu_enabled": True,
    }


def plan_fallback(
    failing_codec: str,
    gpu_caps,
    *,
    gpu_enabled: bool = True,
    history_codec_failures: Optional[dict] = None,
) -> FallbackPlan:
    """Build a ranked fallback chain for a codec that failed
    compatibility.

    Args:
        failing_codec   the codec that failed (e.g. "av1_nvenc").
        gpu_caps        the renderer's gpu_caps snapshot. Optional.
        gpu_enabled     False forces CPU fallbacks only.
        history_codec_failures
                        optional dict mapping codec → recent failure
                        count from QueueStore history. Codecs with
                        many recent failures get demoted.

    Returns FallbackPlan. Empty when no alternative is available
    (e.g. CPU disabled AND no NVENC support — degenerate case).
    """
    caps = _caps_view(gpu_caps)
    history = history_codec_failures or {}

    def fail_count(c: str) -> int:
        return int(history.get(c, 0))

    plan = FallbackPlan()
    if failing_codec == "av1_nvenc":
        if gpu_enabled and caps["hevc_available"] and fail_count("hevc_nvenc") < 3:
            plan.steps.append(
                FallbackStep(
                    codec="hevc_nvenc",
                    reason="hevc_nvenc is the closest GPU substitute and has been stable on this device.",
                    confidence="high",
                )
            )
        if gpu_enabled and caps["h264_available"]:
            plan.steps.append(
                FallbackStep(
                    codec="h264_nvenc",
                    reason="Broader compatibility; lower compression than HEVC/AV1.",
                    confidence="medium",
                )
            )
        plan.steps.append(
            FallbackStep(
                codec="libx265",
                reason="CPU HEVC fallback; slower but always available.",
                confidence="medium",
            )
        )
    elif failing_codec == "hevc_nvenc":
        if gpu_enabled and caps["h264_available"]:
            plan.steps.append(
                FallbackStep(
                    codec="h264_nvenc",
                    reason="H.264 NVENC is universally supported on NVIDIA GPUs.",
                    confidence="high",
                )
            )
        plan.steps.append(
            FallbackStep(
                codec="libx265",
                reason="CPU HEVC fallback.",
                confidence="medium",
            )
        )
    elif failing_codec == "h264_nvenc":
        plan.steps.append(
            FallbackStep(
                codec="libx264",
                reason="CPU fallback for H.264.",
                confidence="high",
            )
        )
    else:
        # Unknown failing codec — best we can do is libx264.
        plan.steps.append(
            FallbackStep(
                codec="libx264",
                reason="Generic CPU fallback.",
                confidence="low",
            )
        )

    plan.note = (
        f"Fallback plan for {failing_codec}. Each step requires "
        "user confirmation; nothing is auto-applied."
    )
    return plan


__all__ = ["FallbackPlan", "FallbackStep", "plan_fallback"]
