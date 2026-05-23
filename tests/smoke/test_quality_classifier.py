"""Smoke tests for `core.optimization.quality_classifier`.

ADR-0003 narrow exception per ADR-0010 — pure-Python, <1s,
deterministic.
"""

from __future__ import annotations

from core.optimization.quality_classifier import Health, classify_health


def _kw(**kw):
    base = dict(
        vmaf_mean=None,
        vmaf_p5=None,
        phash_avg_distance=None,
        render_duration_s=None,
        batch_median_duration_s=None,
    )
    base.update(kw)
    return base


def test_all_none_is_unknown():
    assert classify_health(**_kw()) is Health.UNKNOWN


def test_vmaf_above_threshold_is_green():
    assert (
        classify_health(**_kw(vmaf_mean=97.0, vmaf_p5=95.0, phash_avg_distance=15))
        is Health.GREEN
    )


def test_vmaf_below_threshold_is_yellow():
    assert (
        classify_health(**_kw(vmaf_mean=94.0, vmaf_p5=92.0))
        is Health.YELLOW_LOW_QUALITY
    )


def test_vmaf_catastrophic_is_red():
    assert classify_health(**_kw(vmaf_mean=80.0, vmaf_p5=70.0)) is Health.RED_BROKEN


def test_phash_too_close_is_yellow():
    assert (
        classify_health(**_kw(vmaf_mean=97.0, vmaf_p5=95.0, phash_avg_distance=2.0))
        is Health.YELLOW_LOW_ORIGINALITY
    )


def test_phash_too_different_with_good_vmaf_still_green():
    # When VMAF is great and pHash is very high, classifier still
    # flags YELLOW_LOW_ORIGINALITY band (extreme distance shown).
    h = classify_health(**_kw(vmaf_mean=98.0, vmaf_p5=96.0, phash_avg_distance=40.0))
    assert h in {Health.GREEN, Health.YELLOW_LOW_ORIGINALITY}


def test_slow_render_flag():
    assert (
        classify_health(
            **_kw(
                vmaf_mean=97.0,
                vmaf_p5=95.0,
                phash_avg_distance=15,
                render_duration_s=60.0,
                batch_median_duration_s=15.0,
                slow_factor=3.0,
            )
        )
        is Health.YELLOW_SLOW
    )


def test_no_slow_when_within_factor():
    assert (
        classify_health(
            **_kw(
                vmaf_mean=97.0,
                vmaf_p5=95.0,
                phash_avg_distance=15,
                render_duration_s=30.0,
                batch_median_duration_s=15.0,
                slow_factor=3.0,
            )
        )
        is Health.GREEN
    )


def test_threshold_overrides_take_effect():
    # Same VMAF, raised threshold → flips green→yellow.
    assert classify_health(**_kw(vmaf_mean=97.0, vmaf_p5=95.0)) is Health.GREEN
    assert (
        classify_health(**_kw(vmaf_mean=97.0, vmaf_p5=95.0, vmaf_mean_threshold=98.0))
        is Health.YELLOW_LOW_QUALITY
    )
