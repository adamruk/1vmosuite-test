"""Phase 3.2 — local-only originality/quality scoring system.

This package contains all scoring infrastructure: capability detection,
the four scoring axes (VMAF / SSIM / PSNR / pHash), the persistent
local cache, and the pydantic on-disk schema. Everything in here runs
against the user's own ffmpeg binary and the user's own files. There
is no network code, no remote model download, no upload of any video,
no account, no login. Mirrors the Phase 3.1 local-first contract.

Public surface (re-exports):
    ScoringCapabilities, detect              — capability probe
    ScoreResult                              — pydantic on-disk row
    ScoreCache                               — local JSON cache
    score_vmaf, score_ssim_psnr, score_phash — the three runners

The runners are all sync, blocking calls; the Qt-thread wrapper is the
ScoreWorker QObject inside auto_render.py. Tests for everything here
live under tests/smoke/test_score_*.py (ADR-0003 narrow exception per
ADR-0009 — pure-IO units, no Qt / no GPU / deterministic / <2s).
"""

from __future__ import annotations

from core.scoring.capabilities import ScoringCapabilities, detect
from core.scoring.phash_runner import score_phash
from core.scoring.score_models import (
    SCORE_SCHEMA_VERSION,
    ScoreAxisStatus,
    ScoreResult,
)
from core.scoring.score_store import ScoreCache
from core.scoring.ssim_psnr_runner import score_ssim_psnr
from core.scoring.vmaf_runner import score_vmaf

__all__ = [
    "SCORE_SCHEMA_VERSION",
    "ScoreAxisStatus",
    "ScoreCache",
    "ScoreResult",
    "ScoringCapabilities",
    "detect",
    "score_phash",
    "score_ssim_psnr",
    "score_vmaf",
]
