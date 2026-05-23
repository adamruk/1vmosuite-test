"""Smoke tests for `core.scoring.score_store` (Phase 3.2 cache).

Mirrors the structure of `tests/smoke/test_queue_store.py`. Pure-IO,
no Qt, no ffmpeg. ADR-0003 narrow exception per ADR-0009.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scoring.score_models import (
    SCORE_SCHEMA_VERSION,
    ScoreAxisStatus,
    ScoreResult,
)
from core.scoring.score_store import SCORE_CACHE_FILENAME, ScoreCache


def _make_result(ref: str, dist: str, vmaf_mean: float = 96.0) -> ScoreResult:
    return ScoreResult(
        reference_path=ref,
        reference_mtime=1.0,
        distorted_path=dist,
        distorted_mtime=2.0,
        computed_at=3.0,
        vmaf_status=ScoreAxisStatus.OK,
        vmaf_mean=vmaf_mean,
        vmaf_p5=vmaf_mean - 2.0,
    )


@pytest.fixture
def cache(tmp_path: Path) -> ScoreCache:
    return ScoreCache(user_data_dir=tmp_path)


def test_empty_get_returns_none(cache: ScoreCache):
    assert cache.get("/a", "/b") is None


def test_put_then_get(cache: ScoreCache):
    cache.put(_make_result("/a", "/b", 95.5))
    row = cache.get("/a", "/b")
    assert row is not None
    assert row.vmaf_mean == pytest.approx(95.5)


def test_put_persists_to_disk(cache: ScoreCache, tmp_path: Path):
    cache.put(_make_result("/a", "/b"))
    assert (tmp_path / SCORE_CACHE_FILENAME).is_file()


def test_get_with_stale_mtime_returns_none(cache: ScoreCache):
    cache.put(_make_result("/a", "/b"))
    # reference_mtime in cache is 1.0; supply 999.0 → stale.
    assert cache.get("/a", "/b", reference_mtime=999.0) is None
    # Matching mtimes still return the row.
    assert cache.get("/a", "/b", reference_mtime=1.0) is not None


def test_overwrite_same_key(cache: ScoreCache):
    cache.put(_make_result("/a", "/b", 90.0))
    cache.put(_make_result("/a", "/b", 99.0))
    row = cache.get("/a", "/b")
    assert row is not None
    assert row.vmaf_mean == pytest.approx(99.0)


def test_load_after_reopen(tmp_path: Path):
    c1 = ScoreCache(user_data_dir=tmp_path)
    c1.put(_make_result("/a", "/b", 91.5))
    # Second instance reads from disk.
    c2 = ScoreCache(user_data_dir=tmp_path)
    row = c2.get("/a", "/b")
    assert row is not None
    assert row.vmaf_mean == pytest.approx(91.5)


def test_corrupt_json_returns_empty(tmp_path: Path):
    (tmp_path / SCORE_CACHE_FILENAME).write_text("{not json", encoding="utf-8")
    c = ScoreCache(user_data_dir=tmp_path)
    assert c.get("/a", "/b") is None
    assert len(c) == 0


def test_schema_mismatch_returns_empty(tmp_path: Path):
    # Write a payload with a wrong schema_version.
    payload = {"schema_version": 99, "rows": {}}
    (tmp_path / SCORE_CACHE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    c = ScoreCache(user_data_dir=tmp_path)
    assert len(c) == 0


def test_clear_removes_file(cache: ScoreCache, tmp_path: Path):
    cache.put(_make_result("/a", "/b"))
    assert (tmp_path / SCORE_CACHE_FILENAME).is_file()
    cache.clear()
    assert not (tmp_path / SCORE_CACHE_FILENAME).is_file()
    assert len(cache) == 0


def test_keying_distinct(cache: ScoreCache):
    cache.put(_make_result("/a", "/x", 80.0))
    cache.put(_make_result("/b", "/x", 90.0))
    a = cache.get("/a", "/x")
    b = cache.get("/b", "/x")
    assert a is not None and a.vmaf_mean == pytest.approx(80.0)
    assert b is not None and b.vmaf_mean == pytest.approx(90.0)


def test_rows_iteration(cache: ScoreCache):
    cache.put(_make_result("/a", "/b"))
    cache.put(_make_result("/c", "/d"))
    rows = list(cache.rows())
    assert len(rows) == 2
    # Each row is (key, ScoreResult).
    for _key, val in rows:
        assert isinstance(val, ScoreResult)


def test_schema_version_round_trips(cache: ScoreCache, tmp_path: Path):
    cache.put(_make_result("/a", "/b"))
    on_disk = json.loads((tmp_path / SCORE_CACHE_FILENAME).read_text("utf-8"))
    assert on_disk["schema_version"] == SCORE_SCHEMA_VERSION
