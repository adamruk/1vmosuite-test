"""Smoke test for gpu_detect.detect() capability gating (A4 fix-pass).

A4: gpu_detect.detect() coupled H.264 NVENC availability to the HEVC
hardware signal (`h264_available = hw_supports_hevc and codecs.h264`), so a
pre-Turing NVENC GPU (Pascal/Maxwell — H.264 NVENC capable, no HEVC) with
h264_nvenc present in ffmpeg wrongly reported H.264 as unavailable. H.264
NVENC should unlock from its own ffmpeg-probe signal regardless of HEVC.

Pure logic: both hardware/ffmpeg probes are monkeypatched, so no real GPU,
ffmpeg, or Qt is touched. ADR-0003 narrow exception (deterministic, <2s,
single-purpose regression coverage of a confirmed bug).
"""

from __future__ import annotations

from pathlib import Path

import gpu_detect
from gpu_detect import GPUDevice, GPUGeneration, NvencCodecs


def _patch(monkeypatch, *, generation: GPUGeneration, codecs: NvencCodecs) -> None:
    """Force detect() to see one NVIDIA device of `generation` and the given
    ffmpeg encoder set, without probing real hardware."""
    devices = [
        GPUDevice(
            index=0,
            name="test-gpu",
            generation=generation,
            compute_capability=(6, 1),
            vram_total_mb=8192,
        )
    ]
    monkeypatch.setattr(gpu_detect, "_probe_pynvml", lambda: (devices, "555.00", None))
    monkeypatch.setattr(gpu_detect, "_probe_ffmpeg_encoders", lambda _p: (codecs, None))


def test_h264_decoupled_from_hevc_on_pre_turing(monkeypatch):
    """Pascal (PRE_TURING): h264_nvenc in ffmpeg, no HEVC hardware support.

    Repro for A4 — the buggy gate (`hw_supports_hevc and codecs.h264`)
    returns h264_available=False here because Pascal is below the HEVC
    hardware floor. Correct behavior: H.264 unlocks from its own ffmpeg
    signal, independent of the HEVC gate.
    """
    _patch(
        monkeypatch,
        generation=GPUGeneration.PRE_TURING,
        codecs=NvencCodecs(h264=True, hevc=False, av1=False),
    )
    caps = gpu_detect.detect(Path("dummy-ffmpeg"))

    assert caps.has_nvidia is True
    assert caps.h264_available is True  # was False on buggy code (the A4 bug)
    assert caps.hevc_available is False  # Pascal genuinely lacks HEVC NVENC
    assert caps.nvenc_available is True


def test_ada_full_codec_matrix_unchanged(monkeypatch):
    """Regression guard: Ada with all three encoders keeps all three.

    Passes before and after the fix; ensures decoupling H.264 does not
    disturb the HEVC/AV1 gating that legitimately uses the hardware gen.
    """
    _patch(
        monkeypatch,
        generation=GPUGeneration.ADA,
        codecs=NvencCodecs(h264=True, hevc=True, av1=True),
    )
    caps = gpu_detect.detect(Path("dummy-ffmpeg"))

    assert caps.h264_available is True
    assert caps.hevc_available is True
    assert caps.av1_available is True
