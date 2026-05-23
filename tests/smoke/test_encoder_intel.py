"""Smoke tests for `core.encoder_intel.*`. ADR-0003 narrow per ADR-0012."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.encoder_intel import (
    Severity,
    classify_preset,
    compatibility_check,
    nvenc_session_budget,
    plan_fallback,
)


@dataclass
class FakeCaps:
    h264_available: bool = True
    hevc_available: bool = True
    av1_available: bool = False  # default: Ampere-style
    nvenc_session_cap: int = 3
    driver_version: Optional[str] = "537.13"
    gpu_generation: str = "Ampere"


# ----- classify_preset -----


def test_classify_detects_h264_nvenc():
    c = classify_preset("builtin:cycles/1080p", ["-c:v", "h264_nvenc", "-cq", "23"])
    assert c.codec_family == "h264_nvenc"
    assert c.needs_nvenc_session is True
    assert c.uses_cq is True


def test_classify_detects_av1_nvenc():
    c = classify_preset("custom/av1", ["-c:v", "av1_nvenc"])
    assert c.codec_family == "av1_nvenc"
    assert c.needs_nvenc_session is True


def test_classify_detects_libx264():
    c = classify_preset("p/foo", ["-c:v", "libx264", "-crf", "20"])
    assert c.codec_family == "libx264"
    assert c.uses_cq is True
    assert c.needs_nvenc_session is False


def test_classify_text_overlay_from_id():
    c = classify_preset("builtin:text/text-bottom-basic", ["-vf", "drawtext=..."])
    assert c.codec_family == "text"
    assert c.needs_nvenc_session is False


def test_classify_other():
    c = classify_preset("x/y", ["-vf", "boxblur=10"])
    assert c.codec_family == "other"


# ----- compatibility_check -----


def test_av1_on_ampere_is_block():
    c = classify_preset("p", ["-c:v", "av1_nvenc"])
    v = compatibility_check(c, FakeCaps(av1_available=False, gpu_generation="Ampere"))
    assert v.severity is Severity.BLOCK
    assert v.suggested_fallback_codec in {"hevc_nvenc", "libx265"}


def test_av1_on_ada_is_info():
    c = classify_preset("p", ["-c:v", "av1_nvenc"])
    v = compatibility_check(c, FakeCaps(av1_available=True, gpu_generation="Ada"))
    assert v.severity is Severity.INFO
    assert v.ok is True


def test_hevc_with_gpu_disabled_is_block():
    c = classify_preset("p", ["-c:v", "hevc_nvenc"])
    v = compatibility_check(c, FakeCaps(), gpu_enabled=False)
    assert v.severity is Severity.BLOCK


def test_libx264_always_passes():
    c = classify_preset("p", ["-c:v", "libx264"])
    v = compatibility_check(c, FakeCaps(), gpu_enabled=False)
    assert v.severity is Severity.INFO
    assert v.ok is True


def test_text_preset_always_passes():
    c = classify_preset("builtin:text/x", ["-vf", "drawtext=..."])
    v = compatibility_check(c, FakeCaps())
    assert v.severity is Severity.INFO


# ----- nvenc_session_budget -----


def test_budget_unsaturated():
    assert nvenc_session_budget(0, FakeCaps(nvenc_session_cap=3)) == 3
    assert nvenc_session_budget(2, FakeCaps(nvenc_session_cap=3)) == 1


def test_budget_floor_zero():
    assert nvenc_session_budget(10, FakeCaps(nvenc_session_cap=3)) == 0


# ----- plan_fallback -----


def test_fallback_av1_on_ampere_recommends_hevc():
    plan = plan_fallback("av1_nvenc", FakeCaps(av1_available=False))
    primary = plan.primary()
    assert primary is not None
    assert primary.codec == "hevc_nvenc"


def test_fallback_with_history_demotes_flaky_codec():
    # 6 recent hevc_nvenc failures → drop it from the chain.
    plan = plan_fallback(
        "av1_nvenc",
        FakeCaps(av1_available=False),
        history_codec_failures={"hevc_nvenc": 6},
    )
    codecs = [s.codec for s in plan.steps]
    assert "hevc_nvenc" not in codecs


def test_fallback_h264_recommends_libx264():
    plan = plan_fallback("h264_nvenc", FakeCaps())
    assert plan.primary().codec == "libx264"


def test_fallback_with_gpu_disabled_only_cpu():
    plan = plan_fallback("av1_nvenc", FakeCaps(), gpu_enabled=False)
    for step in plan.steps:
        assert "_nvenc" not in step.codec


def test_fallback_unknown_codec_returns_libx264():
    plan = plan_fallback("mystery_codec", FakeCaps())
    assert plan.primary().codec == "libx264"
