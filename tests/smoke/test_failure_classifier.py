"""Smoke tests for `core.optimization.failure_classifier`.

ADR-0003 narrow exception per ADR-0010 — pure-Python regex, <1s.
"""

from __future__ import annotations

from core.optimization.failure_classifier import classify_failure
from core.optimization.recommendation_models import (
    Confidence,
    RecommendationKind,
)


def test_empty_returns_unknown():
    r = classify_failure(None)
    assert r.kind is RecommendationKind.UNKNOWN
    assert r.confidence is Confidence.LOW


def test_no_such_file():
    r = classify_failure("No such file or directory: /tmp/foo.mp4")
    assert r.kind is RecommendationKind.DEBUG_LOG
    assert "Input file" in r.reason


def test_out_of_memory():
    r = classify_failure("Cannot allocate memory for buffer pool")
    assert r.kind is RecommendationKind.RETRY_AS_IS
    assert r.proposed_params.get("num_threads_delta") == -1


def test_experimental_encoder():
    r = classify_failure("Encoder hevc_nvenc is experimental")
    assert r.kind is RecommendationKind.SWITCH_ENCODER


def test_nvenc_out_of_sessions():
    r = classify_failure("NvEnc: Out of sessions")
    assert r.kind is RecommendationKind.USE_CPU
    assert r.proposed_params.get("gpu_enabled") is False


def test_driver_unsupported():
    r = classify_failure("Driver does not support the required NvEnc version")
    assert r.kind is RecommendationKind.SWITCH_ENCODER
    assert r.proposed_params.get("gpu_codec") == "hevc_nvenc"


def test_io_timeout():
    r = classify_failure("ffmpeg: I/O error reading stream")
    assert r.kind is RecommendationKind.RETRY_AS_IS


def test_cannot_load_cuda():
    r = classify_failure("Cannot load nvcuda.dll")
    assert r.kind is RecommendationKind.USE_CPU


def test_init_encoder_failed():
    r = classify_failure("InitializeEncoder failed: 8 (unsupported)")
    assert r.kind is RecommendationKind.SWITCH_ENCODER
    assert r.proposed_params.get("gpu_preset") == "p4"


def test_unknown_pattern_returns_unknown():
    r = classify_failure("Some completely novel ffmpeg warning xyz")
    assert r.kind is RecommendationKind.UNKNOWN


def test_never_raises_on_garbage_input():
    # Defensive: must not raise on bytes-like nonsense.
    r = classify_failure("\x00\x01 not-text \xff")
    assert r is not None
