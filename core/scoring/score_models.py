"""Phase 3.2 — pydantic v2 schema for the scoring cache on disk.

Mirrors `core/queue_models.py`. One ScoreResult per (reference,
distorted) pair. Schema versioned from day 1 so a future axis can
land without breaking users' existing caches: bump SCORE_SCHEMA_VERSION
and the store's load() will reject incompatible payloads cleanly
(returns None + logs a warning).

Cache key (computed by ScoreCache, not stored as a field):
    sha256(reference_path + "\x00" + distorted_path)
Plus we store the mtime of both files alongside so an in-place
re-render invalidates the cached score automatically.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Bump on any incompatible change to ScoreResult.
SCORE_SCHEMA_VERSION = 1


class ScoreAxisStatus(str, Enum):
    """Lifecycle status of one scoring axis on one task.

    UI maps these to the visible cell content:
        PENDING    -> "—"
        RUNNING    -> "…"
        OK         -> the numeric value
        UNSUPPORTED-> "—" with capability tooltip
        ERROR      -> "ERR" with error tooltip
        CANCELLED  -> "—"
    """

    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    CANCELLED = "cancelled"


class ScoreResult(BaseModel):
    """One scoring row — all axes for one (reference, distorted) pair.

    Fields without values are None — used by the UI to render the
    "—" placeholder for axes that were not requested or not available.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCORE_SCHEMA_VERSION)

    # Identity — the (reference, distorted) pair.
    reference_path: str
    reference_mtime: float
    distorted_path: str
    distorted_mtime: float

    # When this row was last (re)computed; epoch seconds.
    computed_at: float

    # ---- VMAF axis (libvmaf) ----
    vmaf_status: ScoreAxisStatus = ScoreAxisStatus.PENDING
    vmaf_mean: Optional[float] = None
    vmaf_p5: Optional[float] = None
    vmaf_min: Optional[float] = None
    vmaf_max: Optional[float] = None
    vmaf_error: Optional[str] = None

    # ---- SSIM axis ----
    ssim_status: ScoreAxisStatus = ScoreAxisStatus.PENDING
    ssim_mean: Optional[float] = None
    ssim_error: Optional[str] = None

    # ---- PSNR axis ----
    psnr_status: ScoreAxisStatus = ScoreAxisStatus.PENDING
    psnr_mean: Optional[float] = None
    psnr_error: Optional[str] = None

    # ---- pHash axis ----
    phash_status: ScoreAxisStatus = ScoreAxisStatus.PENDING
    # Average and max Hamming distance across sampled frame pairs.
    # Higher = more visually different from the reference. The user's
    # "originality" axis lives here.
    phash_avg_distance: Optional[float] = None
    phash_max_distance: Optional[int] = None
    phash_frames_compared: Optional[int] = None
    phash_error: Optional[str] = None


__all__ = [
    "SCORE_SCHEMA_VERSION",
    "ScoreAxisStatus",
    "ScoreResult",
]
