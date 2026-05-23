"""Smoke tests for `core.optimization.recommender`.

ADR-0003 narrow exception per ADR-0010.
"""

from __future__ import annotations

from core.optimization.recommendation_models import RecommendationKind
from core.optimization.recommender import recommend_for_render


def test_clean_render_returns_empty():
    """Green VMAF + moderate pHash + reasonable speed → no recs."""
    out = recommend_for_render(
        vmaf_mean=98.0,
        vmaf_p5=95.0,
        phash_avg_distance=15.0,
        render_duration_s=20.0,
        batch_median_duration_s=20.0,
    )
    assert out == []


def test_low_vmaf_emits_raise_quality():
    out = recommend_for_render(
        vmaf_mean=90.0, vmaf_p5=85.0, phash_avg_distance=15.0, render_duration_s=20.0
    )
    kinds = {r.kind for r in out}
    assert RecommendationKind.RAISE_QUALITY in kinds


def test_low_phash_emits_increase_difference():
    out = recommend_for_render(
        vmaf_mean=98.0,
        vmaf_p5=95.0,
        phash_avg_distance=2.0,
        render_duration_s=20.0,
    )
    assert any(r.kind is RecommendationKind.INCREASE_DIFFERENCE for r in out)


def test_high_phash_with_low_vmaf_emits_decrease_difference():
    out = recommend_for_render(
        vmaf_mean=90.0,
        vmaf_p5=86.0,
        phash_avg_distance=40.0,
        render_duration_s=20.0,
    )
    kinds = {r.kind for r in out}
    # Both raise_quality + decrease_difference may fire.
    assert RecommendationKind.DECREASE_DIFFERENCE in kinds


def test_slow_render_emits_use_gpu_when_gpu_disabled():
    out = recommend_for_render(
        vmaf_mean=98.0,
        vmaf_p5=95.0,
        phash_avg_distance=15.0,
        render_duration_s=60.0,
        batch_median_duration_s=15.0,
        settings_snapshot={"gpu_enabled": False},
    )
    assert any(r.kind is RecommendationKind.USE_GPU for r in out)


def test_slow_render_does_not_emit_use_gpu_when_gpu_enabled():
    out = recommend_for_render(
        vmaf_mean=98.0,
        vmaf_p5=95.0,
        phash_avg_distance=15.0,
        render_duration_s=60.0,
        batch_median_duration_s=15.0,
        settings_snapshot={"gpu_enabled": True},
    )
    assert not any(r.kind is RecommendationKind.USE_GPU for r in out)


def test_sort_order_quality_before_speed():
    """When both RAISE_QUALITY and USE_GPU fire, quality comes first."""
    out = recommend_for_render(
        vmaf_mean=90.0,
        vmaf_p5=85.0,
        phash_avg_distance=15.0,
        render_duration_s=60.0,
        batch_median_duration_s=15.0,
        settings_snapshot={"gpu_enabled": False},
    )
    kinds = [r.kind for r in out]
    if (
        RecommendationKind.RAISE_QUALITY in kinds
        and RecommendationKind.USE_GPU in kinds
    ):
        assert kinds.index(RecommendationKind.RAISE_QUALITY) < kinds.index(
            RecommendationKind.USE_GPU
        )


def test_threshold_override_changes_outcome():
    # Same VMAF mean; raise threshold → recommendation appears.
    no_rec = recommend_for_render(vmaf_mean=96.5, vmaf_p5=94.0, phash_avg_distance=15.0)
    with_rec = recommend_for_render(
        vmaf_mean=96.5,
        vmaf_p5=94.0,
        phash_avg_distance=15.0,
        vmaf_mean_threshold=98.0,
    )
    assert no_rec == []
    assert with_rec != []


def test_preserves_original_preset_ids():
    out = recommend_for_render(
        vmaf_mean=90.0,
        vmaf_p5=85.0,
        phash_avg_distance=15.0,
        original_preset_ids=["builtin:x/y"],
    )
    assert all(
        r.original_preset_ids == ["builtin:x/y"]
        for r in out
        if r.kind != RecommendationKind.USE_GPU or r.original_preset_ids
    )


def test_recommendations_are_recommendation_instances():
    out = recommend_for_render(vmaf_mean=80.0, vmaf_p5=70.0, phash_avg_distance=15.0)
    for r in out:
        assert r.reason
        assert r.confidence is not None
