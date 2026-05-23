"""Phase 3.5 — schema for encoder intelligence outputs.

Schema-versioned from day 1 so a future bump rejects stale caches
cleanly per the queue_store / score_store contract.
"""

from __future__ import annotations

from enum import Enum

INTEL_SCHEMA_VERSION = 1


class CodecFamily(str, Enum):
    H264_NVENC = "h264_nvenc"
    HEVC_NVENC = "hevc_nvenc"
    AV1_NVENC = "av1_nvenc"
    LIBX264 = "libx264"
    LIBX265 = "libx265"
    IMAGE = "image"
    TEXT = "text"
    OTHER = "other"


__all__ = ["CodecFamily", "INTEL_SCHEMA_VERSION"]
