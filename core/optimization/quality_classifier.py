"""Phase 3.3 — pure quality classifier.

Given a ScoreResult + render duration + batch median, classify
the render's "health" into a fixed enum the UI can colour-band.
Thresholds default to ADR-0008 (VMAF mean >= 96, p5 >= 93). Both
are settings-tunable in Phase 3.3's Optimization tab.

No Qt. No ffmpeg. Pure function over plain types. Trivially
testable.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Health(str, Enum):
    """Render-health classification used by the UI + recommender."""

    GREEN = "green"
    YELLOW_LOW_QUALITY = "yellow_low_quality"
    YELLOW_LOW_ORIGINALITY = "yellow_low_originality"
    YELLOW_SLOW = "yellow_slow"
    RED_BROKEN = "red_broken"
    UNKNOWN = "unknown"


def classify_health(
    *,
    vmaf_mean: Optional[float],
    vmaf_p5: Optional[float],
    phash_avg_distance: Optional[float],
    render_duration_s: Optional[float],
    batch_median_duration_s: Optional[float] = None,
    vmaf_mean_threshold: float = 96.0,
    vmaf_p5_threshold: float = 93.0,
    phash_too_similar: float = 5.0,
    phash_too_different: float = 30.0,
    slow_factor: float = 3.0,
) -> Health:
    """Classify a render's health.

    Args:
        vmaf_mean, vmaf_p5, phash_avg_distance — from ScoreResult.
            Any can be None if that axis was not computed.
        render_duration_s — completed_at - started_at; None if
            the render is still in flight (rare in this path).
        batch_median_duration_s — for slow detection; None
            disables the slow-test branch.
        vmaf_mean_threshold / vmaf_p5_threshold — ADR-0008 floor.
        phash_too_similar / phash_too_different — originality
            band edges.
        slow_factor — duration / median above which the render
            is flagged slow.

    Returns:
        Health enum. UNKNOWN when neither VMAF nor pHash is
        present (cannot decide).
    """
    have_quality = vmaf_mean is not None or vmaf_p5 is not None
    have_originality = phash_avg_distance is not None
    if not have_quality and not have_originality:
        return Health.UNKNOWN

    # Quality floor — a hard RED. We require BOTH a value being
    # present AND it being clearly below threshold. A missing axis
    # is not treated as broken.
    if vmaf_mean is not None and vmaf_mean < (vmaf_mean_threshold - 6.0):
        return Health.RED_BROKEN
    if vmaf_p5 is not None and vmaf_p5 < (vmaf_p5_threshold - 8.0):
        return Health.RED_BROKEN

    # Yellow: quality below ADR-0008 floor but not catastrophically.
    if vmaf_mean is not None and vmaf_mean < vmaf_mean_threshold:
        return Health.YELLOW_LOW_QUALITY
    if vmaf_p5 is not None and vmaf_p5 < vmaf_p5_threshold:
        return Health.YELLOW_LOW_QUALITY

    # Yellow: too close to source (low originality).
    if phash_avg_distance is not None and phash_avg_distance < phash_too_similar:
        return Health.YELLOW_LOW_ORIGINALITY

    # Yellow: too different (likely over-processed). Note we use
    # the "broken" band here — extreme pHash distance with low
    # VMAF would already have flagged RED above; here it's a soft
    # warning.
    if phash_avg_distance is not None and phash_avg_distance > phash_too_different:
        return Health.YELLOW_LOW_ORIGINALITY  # surfaces same band

    # Yellow: slow render relative to batch median.
    if (
        render_duration_s is not None
        and batch_median_duration_s is not None
        and batch_median_duration_s > 0
        and render_duration_s > batch_median_duration_s * slow_factor
    ):
        return Health.YELLOW_SLOW

    return Health.GREEN


__all__ = ["Health", "classify_health"]
