"""Smoke tests for `core.optimization.batch_analyzer`.

ADR-0003 narrow exception per ADR-0010.
"""

from __future__ import annotations

from core.optimization.batch_analyzer import analyze_batch


def _row(**kw):
    base = dict(
        vmaf_mean=None,
        vmaf_p5=None,
        phash_avg_distance=None,
        duration_s=None,
        status="completed",
        error_message=None,
    )
    base.update(kw)
    return base


def test_empty_batch():
    s = analyze_batch(rows=[])
    assert s.total == 0
    assert s.green == s.yellow == s.red == s.unknown == s.failed == 0
    assert s.median_duration_s is None


def test_all_green_batch():
    rows = [
        _row(vmaf_mean=97.0, vmaf_p5=94.0, phash_avg_distance=15.0, duration_s=20)
        for _ in range(3)
    ]
    s = analyze_batch(rows=rows)
    assert s.total == 3
    assert s.green == 3
    assert s.yellow == 0
    assert s.red == 0
    assert s.median_duration_s == 20.0


def test_mixed_batch_buckets_correctly():
    rows = [
        _row(vmaf_mean=98.0, vmaf_p5=95.0, phash_avg_distance=15.0, duration_s=20),
        _row(vmaf_mean=94.0, vmaf_p5=90.0, phash_avg_distance=15.0, duration_s=22),
        _row(vmaf_mean=80.0, vmaf_p5=70.0, phash_avg_distance=15.0, duration_s=22),
        _row(status="failed", error_message="NvEnc: out of sessions"),
    ]
    s = analyze_batch(rows=rows)
    assert s.total == 4
    assert s.green == 1
    assert s.yellow == 1
    assert s.red == 1
    assert s.failed == 1
    assert "NvEnc" in s.most_common_error


def test_median_with_odd_and_even():
    rows = [_row(duration_s=d, vmaf_mean=98.0) for d in [10, 20, 30]]
    s = analyze_batch(rows=rows)
    assert s.median_duration_s == 20.0
    rows4 = [_row(duration_s=d, vmaf_mean=98.0) for d in [10, 20, 30, 40]]
    s4 = analyze_batch(rows=rows4)
    assert s4.median_duration_s == 25.0


def test_notes_for_quality_problems():
    rows = [
        _row(vmaf_mean=90.0, vmaf_p5=85.0, phash_avg_distance=15.0, duration_s=20),
        _row(vmaf_mean=91.0, vmaf_p5=86.0, phash_avg_distance=15.0, duration_s=20),
    ]
    s = analyze_batch(rows=rows)
    assert any("below VMAF" in n for n in s.notes)


def test_notes_for_phash_too_close():
    rows = [
        _row(vmaf_mean=97.0, vmaf_p5=94.0, phash_avg_distance=2.0, duration_s=20),
        _row(vmaf_mean=97.0, vmaf_p5=94.0, phash_avg_distance=3.0, duration_s=20),
    ]
    s = analyze_batch(rows=rows)
    assert any("pHash" in n for n in s.notes)


def test_notes_for_slow_outlier():
    rows = [
        _row(vmaf_mean=97.0, vmaf_p5=94.0, duration_s=10),
        _row(vmaf_mean=97.0, vmaf_p5=94.0, duration_s=10),
        _row(vmaf_mean=97.0, vmaf_p5=94.0, duration_s=10),
        _row(vmaf_mean=97.0, vmaf_p5=94.0, duration_s=60),
    ]
    s = analyze_batch(rows=rows)
    assert any("Slowest" in n for n in s.notes)


def test_unknown_when_no_axes_present():
    rows = [_row(duration_s=20)]
    s = analyze_batch(rows=rows)
    assert s.unknown == 1


def test_avg_vmaf_and_phash():
    rows = [
        _row(vmaf_mean=96.0, phash_avg_distance=10.0, duration_s=20),
        _row(vmaf_mean=98.0, phash_avg_distance=20.0, duration_s=20),
    ]
    s = analyze_batch(rows=rows)
    assert s.avg_vmaf_mean == 97.0
    assert s.avg_phash_distance == 15.0
