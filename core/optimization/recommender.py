"""Phase 3.3 — pure recommender.

Given the per-task data we already have (ScoreResult + encoder
ids + render duration + a snapshot of relevant settings), return
a sorted list of Recommendations.

Pure function. No I/O, no Qt, no ffmpeg. Deterministic. The
caller wraps each Recommendation in a confirm dialog before any
re-render fires — there is no auto-apply path.
"""

from __future__ import annotations

from typing import Any, Optional

from core.optimization.quality_classifier import Health, classify_health
from core.optimization.recommendation_models import (
    Confidence,
    Recommendation,
    RecommendationKind,
)


def _kind_precedence(kind: RecommendationKind) -> int:
    """Lower number = higher precedence in the sorted output."""
    order = {
        RecommendationKind.RAISE_QUALITY: 0,
        RecommendationKind.USE_CPU: 1,
        RecommendationKind.SWITCH_ENCODER: 2,
        RecommendationKind.INCREASE_DIFFERENCE: 3,
        RecommendationKind.DECREASE_DIFFERENCE: 4,
        RecommendationKind.USE_GPU: 5,
        RecommendationKind.LOWER_QUALITY: 6,
        RecommendationKind.RETRY_AS_IS: 7,
        RecommendationKind.DEBUG_LOG: 8,
        RecommendationKind.UNKNOWN: 9,
    }
    return order.get(kind, 99)


def _confidence_score(c: Confidence) -> int:
    return {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}[c]


def recommend_for_render(
    *,
    vmaf_mean: Optional[float] = None,
    vmaf_p5: Optional[float] = None,
    phash_avg_distance: Optional[float] = None,
    render_duration_s: Optional[float] = None,
    batch_median_duration_s: Optional[float] = None,
    original_preset_ids: Optional[list[str]] = None,
    settings_snapshot: Optional[dict[str, Any]] = None,
    gpu_available: Optional[bool] = None,
    vmaf_mean_threshold: float = 96.0,
    vmaf_p5_threshold: float = 93.0,
    phash_too_similar: float = 5.0,
    phash_too_different: float = 30.0,
) -> list[Recommendation]:
    """Produce a sorted list of Recommendations for one render.

    The arguments mirror ScoreResult + QueueTask + the batch's
    settings_snapshot — every input is a primitive so the
    function is trivially testable.

    Sorting: primary by precedence, secondary by confidence
    (HIGH before MEDIUM before LOW).
    """
    settings = settings_snapshot or {}
    original_preset_ids = list(original_preset_ids or [])
    health = classify_health(
        vmaf_mean=vmaf_mean,
        vmaf_p5=vmaf_p5,
        phash_avg_distance=phash_avg_distance,
        render_duration_s=render_duration_s,
        batch_median_duration_s=batch_median_duration_s,
        vmaf_mean_threshold=vmaf_mean_threshold,
        vmaf_p5_threshold=vmaf_p5_threshold,
        phash_too_similar=phash_too_similar,
        phash_too_different=phash_too_different,
    )

    out: list[Recommendation] = []

    # --- RAISE_QUALITY when VMAF below floor.
    if vmaf_mean is not None and vmaf_mean < vmaf_mean_threshold:
        gap = vmaf_mean_threshold - vmaf_mean
        if gap > 3.0:
            crf_delta = -4
            conf = Confidence.HIGH
        elif gap > 1.0:
            crf_delta = -3
            conf = Confidence.HIGH
        else:
            crf_delta = -2
            conf = Confidence.MEDIUM
        out.append(
            Recommendation(
                kind=RecommendationKind.RAISE_QUALITY,
                reason=(
                    f"VMAF mean {vmaf_mean:.1f} is below the configured "
                    f"floor of {vmaf_mean_threshold:.1f}. Drop CRF by "
                    f"{abs(crf_delta)} or bump the NVENC preset family."
                ),
                confidence=conf,
                delta_summary=f"CRF {crf_delta:+d} / preset family p4 → p6",
                proposed_params={
                    "crf_delta": crf_delta,
                    "preset_family": "p6",
                    "max_quality": True,
                },
                original_preset_ids=original_preset_ids,
            )
        )

    # --- INCREASE_DIFFERENCE when too close to source.
    if phash_avg_distance is not None and phash_avg_distance < phash_too_similar:
        out.append(
            Recommendation(
                kind=RecommendationKind.INCREASE_DIFFERENCE,
                reason=(
                    f"pHash distance {phash_avg_distance:.1f} is very low "
                    f"(threshold {phash_too_similar:.1f}). Consider "
                    "chaining a Text overlay or a small crop/zoom preset."
                ),
                confidence=Confidence.MEDIUM,
                delta_summary="add Text overlay preset",
                proposed_params={
                    "extra_vf": ["drawtext"],
                    "chain_text_preset": True,
                },
                original_preset_ids=original_preset_ids,
            )
        )

    # --- DECREASE_DIFFERENCE when over-processed.
    if (
        phash_avg_distance is not None
        and phash_avg_distance > phash_too_different
        and vmaf_mean is not None
        and vmaf_mean < vmaf_mean_threshold
    ):
        out.append(
            Recommendation(
                kind=RecommendationKind.DECREASE_DIFFERENCE,
                reason=(
                    f"pHash distance {phash_avg_distance:.1f} is very high "
                    f"AND VMAF dropped — the render lost too much "
                    "structural content. Consider a milder filter or "
                    "higher bitrate."
                ),
                confidence=Confidence.MEDIUM,
                delta_summary="drop CRF / drop heavy filter",
                proposed_params={"crf_delta": -2},
                original_preset_ids=original_preset_ids,
            )
        )

    # --- USE_GPU when slow + GPU is currently disabled + GPU is
    # actually present. gpu_available=None (caller didn't probe) is
    # treated as available for backward compat; an explicit False
    # suppresses the recommendation on CPU-only machines.
    gpu_enabled = bool(settings.get("gpu_enabled", False))
    if (
        render_duration_s is not None
        and batch_median_duration_s is not None
        and batch_median_duration_s > 0
        and render_duration_s > batch_median_duration_s * 3.0
        and not gpu_enabled
        and gpu_available is not False
    ):
        out.append(
            Recommendation(
                kind=RecommendationKind.USE_GPU,
                reason=(
                    f"This render took {render_duration_s:.0f}s "
                    f"(median {batch_median_duration_s:.0f}s, "
                    f"~{render_duration_s / batch_median_duration_s:.1f}× "
                    "slower). Enabling NVENC typically yields a 3-5× "
                    "speedup with comparable VMAF."
                ),
                confidence=Confidence.MEDIUM,
                delta_summary="GPU enabled, codec hevc_nvenc preset p5",
                proposed_params={
                    "gpu_enabled": True,
                    "gpu_codec": "hevc_nvenc",
                    "gpu_preset": "p5",
                },
                original_preset_ids=original_preset_ids,
            )
        )

    # If health says GREEN and no recommendations, return empty.
    if not out and health is Health.GREEN:
        return []

    out.sort(key=lambda r: (_kind_precedence(r.kind), _confidence_score(r.confidence)))
    return out


__all__ = ["recommend_for_render"]
