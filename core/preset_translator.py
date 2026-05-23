"""CRF -> CQ preset translator for NVENC GPU encoding.

Translates ffmpeg parameter lists from CPU codecs (libx264/libx265) to NVENC
codecs (h264_nvenc/hevc_nvenc/av1_nvenc) per ADR-0007 D2/D3/D7.

Per ADR-0007 D3: CRF -> CQ +2 rule with vbr rate control.
Per ADR-0007 D2: legacy presets (slow/hq/llhq/hp) mapped to p1-p7 family.
Per ADR-0007 D7: multipass=0 default; multipass=2 only when max_quality_mode.

Used by RenderWorker.process() in Step 4d-ii to translate encoder_params before
ffmpeg invocation. encoder_params_original is preserved by the caller for CPU
fallback per ADR-0007 D5.
"""

from core.config import APP_DEFAULTS

# Legacy preset name -> p-family mapping per ADR-0007 D2.
# Phase 1 used this same mapping for translator output; preserved verbatim.
_PRESET_MAP = {
    "ultrafast": "p1",
    "veryfast": "p2",
    "fast": "p3",
    "medium": "p5",
    "slow": "p7",
    "slower": "p7",
    "veryslow": "p7",
}

# CPU codecs eligible for NVENC translation. Per ADR-0015 (single-knob
# routing) only the KEYS are consulted — membership marks a preset codec as
# "translate to the user's gpu_codec". The mapped values are kept for
# documentation/readability only and are NOT used for routing (B-015).
# (ADR-0007 D4 governs the Settings codec DROPDOWN, not this routing.)
_CODEC_MAP = {
    "libx264": "h264_nvenc",
    "libx265": "hevc_nvenc",
    # libsvtav1 / libaom-av1 -> av1_nvenc requires explicit user opt-in via
    # gpu_codec setting; not auto-mapped here. Pass through unchanged.
}

# CRF -> CQ offset per ADR-0007 D3. Per-codec dict (Step 4e-fix-2 calibration).
# Originally scalar +2 (Step 4d-i); empirically calibrated per-codec after Step 4e-fix-1
# validation showed all 3 codecs needed adjustment, not just av1 as ADR-0007 D9 anticipated.
# Values determined by Step 4e-fix-2 retest against 4-clip reference set on RTX 4080.
CRF_TO_CQ_OFFSET = {
    "h264_nvenc": 0,  # was implicit +2; mean 97.92 at +2 -> targeting >= 98.0
    "hevc_nvenc": 0,  # was implicit +2; mean 97.99 at +2 -> targeting >= 98.0
    "av1_nvenc": -1,  # was implicit +2; p5 95.18 at +2 -> targeting >= 97.0
}

# Backward-compat default for any codec not in the dict above (defensive coding):
# falls back to +2 (original ADR-0007 D3 hypothesis) so unknown codecs don't crash.
_CQ_OFFSET_DEFAULT = 2

# NVENC preset + multipass defaults per ADR-0007 D7 "Max Quality Mode" (Step 4e-fix-3).
# Originally hardcoded as preset=p4 + multipass=0 in the orchestrator (Step 4d-i).
# After Step 4e-fix-2 confirmed Path A (offset calibration) hit a quality ceiling at
# p4/multipass=0, ADR-0007 D7 anticipated escalation to "Max Quality Mode": preset=p7
# (slowest/highest-quality NVENC preset family per D2) + multipass=2 (two-pass analysis
# catches p5-tail outliers per D7). Values determined by Step 4e-fix-3 retest against
# the 4-clip reference set on RTX 4080.
NVENC_PRESET_DEFAULT = "p7"
NVENC_MULTIPASS_DEFAULT = "2"


def translate_to_nvenc(
    params: list[str],
    codec: str = APP_DEFAULTS.gpu_codec,
    preset: str = APP_DEFAULTS.gpu_preset,
    max_quality_mode: bool = False,
) -> list[str]:
    """Translate CPU encoder params to NVENC equivalents.

    Args:
        params: ffmpeg parameter list, e.g. ["-c:v", "libx264", "-crf", "20", ...]
        codec: target NVENC codec ("h264_nvenc" / "hevc_nvenc" / "av1_nvenc")
        preset: NVENC preset (p1-p7); default "p4" per ADR-0007 D2
        max_quality_mode: if True, append -multipass 2 per ADR-0007 D7

    Returns:
        Translated parameter list. Unknown codecs / parameters pass through unchanged.
    """
    out: list[str] = []
    i = 0
    saw_preset = False

    while i < len(params):
        p = params[i]

        # -c:v / -vcodec -> route to the user's single gpu_codec setting.
        # Single-knob routing per ADR-0015 (B-015): when the preset names a CPU
        # codec we translate (in _CODEC_MAP, i.e. libx264/libx265), the target
        # NVENC codec is the `codec` kwarg (the gpu_codec setting), NOT a
        # per-preset map. Codecs we don't translate (already-NVENC, av1 sources,
        # etc.) pass through unchanged.
        if p in ("-c:v", "-vcodec") and i + 1 < len(params):
            input_codec = params[i + 1]
            if input_codec in _CODEC_MAP:
                out.extend([p, codec])
            else:
                out.extend([p, input_codec])
            i += 2
            continue

        # -crf -> -cq:v with +2 rule + vbr rate control + b:v 0 trap-avoid
        if p == "-crf" and i + 1 < len(params):
            try:
                crf_value = int(params[i + 1])
                # Per-codec offset lookup (Step 4e-fix-2). Falls back to default if codec unknown.
                offset = (
                    CRF_TO_CQ_OFFSET.get(codec, _CQ_OFFSET_DEFAULT)
                    if isinstance(CRF_TO_CQ_OFFSET, dict)
                    else CRF_TO_CQ_OFFSET
                )
                cq_value = crf_value + offset
                out.extend(["-cq:v", str(cq_value), "-rc:v", "vbr", "-b:v", "0"])
            except ValueError:
                # Non-integer CRF (rare, e.g. fractional); pass through unchanged.
                out.extend([p, params[i + 1]])
            i += 2
            continue

        # -preset -> map legacy name to p-family per ADR-0007 D2
        if p == "-preset" and i + 1 < len(params):
            mapped = _PRESET_MAP.get(params[i + 1], preset)
            out.extend([p, mapped])
            saw_preset = True
            i += 2
            continue

        out.append(p)
        i += 1

    # If input had no -c:v at all, do NOT inject one — caller (RenderWorker) handles
    # default codec injection per existing _has_vcodec check.

    # If input had no -preset, append the default per ADR-0007 D2.
    if not saw_preset:
        out.extend(["-preset", preset])

    # Append -multipass per ADR-0007 D7. multipass=0 default; 2 if max_quality_mode.
    out.extend(["-multipass", "2" if max_quality_mode else "0"])

    return out
