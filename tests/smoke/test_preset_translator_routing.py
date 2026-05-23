"""Characterization tests for NVENC codec routing (B-015 fix-pass).

Pins the SINGLE-KNOB routing decision codified in ADR-0015: when a preset
names a CPU codec the translator recognizes (libx264/libx265), the output
NVENC codec is the user's gpu_codec setting (the `codec` kwarg) — NOT a
per-preset codec map. Unrecognized codecs pass through unchanged.

These tests pass BEFORE and AFTER the B-015 refactor, which only removes the
misleading unused `mapped` variable. They exist to prove the refactor is
behavior-preserving — there is no behavior change, by design.

Pure logic, no Qt/ffmpeg/GPU. ADR-0003 narrow exception (deterministic, <2s).
"""

from __future__ import annotations

from core.config import APP_DEFAULTS
from core.preset_translator import translate_to_nvenc


def _vcodec_value(params: list[str]) -> str:
    idx = params.index("-c:v")
    return params[idx + 1]


def test_libx265_preset_routes_to_gpu_codec_not_hevc():
    """Single-knob: libx265 preset + h264_nvenc setting -> h264_nvenc.

    The exact B-015 scenario — the preset's codec intent (libx265) does NOT
    force hevc_nvenc; the user's gpu_codec choice wins.
    """
    out = translate_to_nvenc(
        ["-c:v", "libx265", "-crf", "20"], codec="h264_nvenc", preset="p4"
    )
    assert _vcodec_value(out) == "h264_nvenc"


def test_libx264_preset_routes_to_gpu_codec_hevc():
    """Inverse: libx264 preset + hevc_nvenc setting -> hevc_nvenc."""
    out = translate_to_nvenc(["-c:v", "libx264"], codec="hevc_nvenc", preset="p4")
    assert _vcodec_value(out) == "hevc_nvenc"


def test_default_gpu_codec_wins_for_recognized_cpu_codec():
    """With no explicit codec kwarg, a recognized CPU codec routes to the
    configured default (APP_DEFAULTS.gpu_codec)."""
    out = translate_to_nvenc(["-c:v", "libx265", "-crf", "18"])
    assert _vcodec_value(out) == APP_DEFAULTS.gpu_codec


def test_unrecognized_codec_passes_through_unchanged():
    """A codec not in _CODEC_MAP (already-NVENC, av1 source, etc.) is left
    untouched regardless of the gpu_codec setting."""
    out = translate_to_nvenc(["-c:v", "libsvtav1"], codec="h264_nvenc")
    assert _vcodec_value(out) == "libsvtav1"

    out2 = translate_to_nvenc(["-c:v", "h264_nvenc"], codec="hevc_nvenc")
    assert _vcodec_value(out2) == "h264_nvenc"
