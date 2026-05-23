"""Smoke tests for `core.scoring.score_models` (Phase 3.2 schema).

ADR-0003 narrow-pytest exception: pure-Python pydantic models with
no Qt / no ffmpeg / no GPU dependency. <1s, deterministic, would
not be replaced by a manual smoke log per ADR-0001's spirit.
"""

from __future__ import annotations

import json

import pytest

from core.scoring.score_models import (
    SCORE_SCHEMA_VERSION,
    ScoreAxisStatus,
    ScoreResult,
)


def _minimal_kwargs(tmp_path):
    return {
        "reference_path": str(tmp_path / "ref.mp4"),
        "reference_mtime": 1.0,
        "distorted_path": str(tmp_path / "dist.mp4"),
        "distorted_mtime": 2.0,
        "computed_at": 3.0,
    }


def test_schema_version_default():
    sr = ScoreResult(
        reference_path="/r",
        reference_mtime=0.0,
        distorted_path="/d",
        distorted_mtime=0.0,
        computed_at=0.0,
    )
    assert sr.schema_version == SCORE_SCHEMA_VERSION


def test_all_status_default_pending(tmp_path):
    sr = ScoreResult(**_minimal_kwargs(tmp_path))
    assert sr.vmaf_status is ScoreAxisStatus.PENDING
    assert sr.ssim_status is ScoreAxisStatus.PENDING
    assert sr.psnr_status is ScoreAxisStatus.PENDING
    assert sr.phash_status is ScoreAxisStatus.PENDING


def test_extra_field_forbidden(tmp_path):
    # extra="forbid" → unknown field rejected.
    kw = _minimal_kwargs(tmp_path)
    kw["bogus_field"] = "value"
    with pytest.raises(Exception):
        ScoreResult(**kw)


def test_round_trip_json(tmp_path):
    sr = ScoreResult(**_minimal_kwargs(tmp_path))
    sr.vmaf_status = ScoreAxisStatus.OK
    sr.vmaf_mean = 96.42
    sr.vmaf_p5 = 94.10
    sr.phash_status = ScoreAxisStatus.OK
    sr.phash_avg_distance = 18.5
    sr.phash_max_distance = 24
    sr.phash_frames_compared = 20
    dumped = sr.model_dump(mode="json")
    # JSON-serializable.
    text = json.dumps(dumped)
    parsed = json.loads(text)
    rehydrated = ScoreResult.model_validate(parsed)
    assert rehydrated.vmaf_mean == pytest.approx(96.42)
    assert rehydrated.phash_max_distance == 24
    assert rehydrated.vmaf_status is ScoreAxisStatus.OK


def test_axis_status_string_enum():
    # str-enum members compare equal to their string value (used by
    # the JSON round-trip in ScoreCache).
    assert ScoreAxisStatus.OK.value == "ok"
    assert ScoreAxisStatus.PENDING == "pending"
