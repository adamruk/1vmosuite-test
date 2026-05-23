"""Phase 3.5 — pure preset classifier + compatibility checker.

No I/O, no Qt, no ffmpeg shell-out. Functions take primitives and
return dataclasses. The caller (auto_render preflight) wraps these
in dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class PresetClassification:
    """Lightweight summary of what an ffmpeg preset is asking for."""

    codec_family: str
    needs_nvenc_session: bool
    uses_cq: bool
    has_explicit_codec: bool


@dataclass
class CompatibilityVerdict:
    """Result of running a preset's classification against gpu caps."""

    ok: bool = True
    severity: Severity = Severity.INFO
    reason: str = ""
    suggested_fallback_codec: Optional[str] = None


# Token sentinels that signal a codec choice in preset params.
_CODEC_TOKENS = {
    "h264_nvenc",
    "hevc_nvenc",
    "av1_nvenc",
    "libx264",
    "libx265",
}


def classify_preset(preset_id: str, params: Iterable[str]) -> PresetClassification:
    """Classify a preset by scanning its params for codec sentinels."""
    plist = list(params or [])
    text = " ".join(plist)
    codec = "other"
    has_explicit = False
    for tok in _CODEC_TOKENS:
        if tok in text:
            codec = tok
            has_explicit = True
            break
    # Heuristic: ID prefix can also reveal intent (e.g. text/image).
    if codec == "other" and preset_id:
        pid = preset_id.lower()
        if "text" in pid:
            codec = "text"
        elif "image" in pid or "layer" in pid:
            codec = "image"
    needs_nvenc = codec.endswith("_nvenc")
    uses_cq = "-cq" in text or "-crf" in text
    return PresetClassification(
        codec_family=codec,
        needs_nvenc_session=needs_nvenc,
        uses_cq=uses_cq,
        has_explicit_codec=has_explicit,
    )


@dataclass
class _CapsView:
    h264_available: bool = True
    hevc_available: bool = True
    av1_available: bool = True
    nvenc_session_cap: int = 3
    driver_version: Optional[str] = None
    gpu_generation: str = "unknown"


def _caps_from(gpu_caps) -> _CapsView:
    """Adapter so this module is decoupled from gpu_detect's exact shape."""
    if gpu_caps is None:
        return _CapsView()
    return _CapsView(
        h264_available=getattr(gpu_caps, "h264_available", True),
        hevc_available=getattr(gpu_caps, "hevc_available", True),
        av1_available=getattr(gpu_caps, "av1_available", True),
        nvenc_session_cap=int(getattr(gpu_caps, "nvenc_session_cap", 3) or 3),
        driver_version=getattr(gpu_caps, "driver_version", None),
        gpu_generation=getattr(gpu_caps, "gpu_generation", "unknown") or "unknown",
    )


def compatibility_check(
    classification: PresetClassification,
    gpu_caps,
    *,
    gpu_enabled: bool = True,
) -> CompatibilityVerdict:
    """Decide whether the preset can run on the user's GPU.

    Returns a verdict with severity:
      BLOCK — preset would fail outright (e.g. av1_nvenc on Pascal).
      WARN  — preset will run but may oversubscribe / be slow.
      INFO  — no issue.
    """
    caps = _caps_from(gpu_caps)
    fam = classification.codec_family
    if fam == "av1_nvenc":
        if not gpu_enabled:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason="av1_nvenc requested but GPU encoding is disabled.",
                suggested_fallback_codec="libx264",
            )
        if not caps.av1_available:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason=(
                    f"av1_nvenc not supported by GPU "
                    f"(generation: {caps.gpu_generation}). Needs Ada or "
                    "newer."
                ),
                suggested_fallback_codec="hevc_nvenc"
                if caps.hevc_available
                else "libx265",
            )
    if fam == "hevc_nvenc":
        if not gpu_enabled:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason="hevc_nvenc requested but GPU encoding is disabled.",
                suggested_fallback_codec="libx265",
            )
        if not caps.hevc_available:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason="hevc_nvenc not supported on this GPU.",
                suggested_fallback_codec="libx265",
            )
    if fam == "h264_nvenc":
        if not gpu_enabled:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason="h264_nvenc requested but GPU encoding is disabled.",
                suggested_fallback_codec="libx264",
            )
        if not caps.h264_available:
            return CompatibilityVerdict(
                ok=False,
                severity=Severity.BLOCK,
                reason="h264_nvenc not supported on this GPU.",
                suggested_fallback_codec="libx264",
            )
    return CompatibilityVerdict(ok=True, severity=Severity.INFO)


def nvenc_session_budget(running_tasks: int, gpu_caps) -> int:
    """How many more NVENC sessions can be dispatched.

    Caller passes the count of currently-running NVENC tasks; we
    subtract from the probed session cap and floor at 0.
    """
    caps = _caps_from(gpu_caps)
    return max(0, caps.nvenc_session_cap - int(running_tasks))


__all__ = [
    "CompatibilityVerdict",
    "PresetClassification",
    "Severity",
    "classify_preset",
    "compatibility_check",
    "nvenc_session_budget",
]
