"""Phase 3.2 — scoring capability probe.

Mirrors `gpu_detect._probe_ffmpeg_encoders`: parse `ffmpeg -filters`
once at startup and remember which scoring axes the bundled ffmpeg
can serve.

Why probe at startup, not per-render:
    `ffmpeg -filters` is ~50 ms on a warm cache. Doing it once and
    caching in `self.scoring_caps` keeps the per-render hot path
    untouched (Phase 2d invariant: render dispatch should not pay
    for any feature it doesn't use).

What we probe:
    - libvmaf  — required for VMAF. Bundled ffmpeg may or may not
                 carry it; older or stripped builds omit it.
    - ssim     — built into every reasonable ffmpeg, but probe
                 anyway so we degrade gracefully if a user dropped
                 in a custom stripped binary.
    - psnr     — same.

pHash is not probed here because it doesn't need ffmpeg at all
beyond raw-frame extraction (-vf scale + image2pipe) which every
ffmpeg supports. Pillow handles the decode + dHash computation in
pure Python.

Local-only: subprocess.run on the user's ffmpeg, parse stdout,
return a dataclass. No network anywhere.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import ffmpeg_runner as core_ffmpeg_runner

logger = logging.getLogger("core.scoring.capabilities")

# `ffmpeg -filters` prints lines of the form:
#   ` T.. libvmaf       VV->V    Calculate the VMAF...`
#   ` TS  ssim          VV->V    Calculate the SSIM...`
# v3.9 H1 fix: bundled ffmpeg emits a flag column of variable width.
# Some builds print 3 characters (e.g. "T..") with no trailing spaces;
# others print 2 characters (e.g. "TS") followed by extra whitespace.
# Older regex `[A-Z.]{3}` only matched the 3-char form, so SSIM/PSNR
# were silently classified as unavailable on those builds.
_FILTER_LINE = re.compile(
    r"^\s*[A-Z.]{2,3}\s+([A-Za-z0-9_]+)\s+[A-Z|]+->[A-Z|]+", re.MULTILINE
)

# Filters we care about for Phase 3.2.
_TARGET_FILTERS = frozenset({"libvmaf", "ssim", "psnr"})


@dataclass
class ScoringCapabilities:
    """Snapshot of which scoring axes the bundled ffmpeg can run."""

    vmaf_available: bool = False
    ssim_available: bool = False
    psnr_available: bool = False
    # pHash needs Pillow + raw-frame extraction; both are always
    # available on supported platforms. The flag is here for
    # symmetry + so a future build that strips Pillow can flip it.
    phash_available: bool = True
    # Best-effort populated by detect() — None if probe failed.
    ffmpeg_version: Optional[str] = None
    # The probe error (if any) so the UI can show a helpful tooltip.
    probe_error: Optional[str] = None
    # Raw filter names discovered, for debugging.
    discovered_filters: frozenset[str] = field(default_factory=frozenset)

    def any_axis_available(self) -> bool:
        """True if at least one axis can score. UI gates on this."""
        return (
            self.vmaf_available
            or self.ssim_available
            or self.psnr_available
            or self.phash_available
        )

    def summary(self) -> str:
        """One-line human summary for tooltips and logs."""
        axes = []
        if self.vmaf_available:
            axes.append("VMAF")
        if self.ssim_available:
            axes.append("SSIM")
        if self.psnr_available:
            axes.append("PSNR")
        if self.phash_available:
            axes.append("pHash")
        if not axes:
            return "no scoring axes available"
        return "available axes: " + ", ".join(axes)


def detect(ffmpeg_path: Path) -> ScoringCapabilities:
    """Probe the bundled ffmpeg for scoring filters.

    Safe at startup: never raises. On any probe failure
    (binary missing, timeout, permission denied) returns a
    capabilities object with all ffmpeg-based flags False and
    `probe_error` populated. pHash is left True because it doesn't
    depend on ffmpeg filters.
    """
    caps = ScoringCapabilities()
    if not ffmpeg_path.is_file():
        caps.probe_error = f"ffmpeg not found at {ffmpeg_path}"
        logger.warning("scoring_caps: %s", caps.probe_error)
        return caps
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=core_ffmpeg_runner.hidden_creationflags(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        caps.probe_error = "ffmpeg -filters timed out"
        logger.warning("scoring_caps: %s", caps.probe_error)
        return caps
    except OSError as exc:
        caps.probe_error = f"ffmpeg probe failed: {exc}"
        logger.warning("scoring_caps: %s", caps.probe_error)
        return caps
    # Capability output goes to stdout on success; some ffmpeg builds
    # mix it onto stderr. Concat both — it's read-only text.
    haystack = (result.stdout or "") + "\n" + (result.stderr or "")
    found: set[str] = set()
    for match in _FILTER_LINE.finditer(haystack):
        name = match.group(1)
        if name in _TARGET_FILTERS:
            found.add(name)
    caps.discovered_filters = frozenset(found)
    caps.vmaf_available = "libvmaf" in found
    caps.ssim_available = "ssim" in found
    caps.psnr_available = "psnr" in found
    # Also pull the ffmpeg version banner for diagnostics. Best
    # effort — if -version fails, leave None and continue.
    try:
        ver = subprocess.run(
            [str(ffmpeg_path), "-hide_banner", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=core_ffmpeg_runner.hidden_creationflags(),
            check=False,
        )
        if ver.returncode == 0 and ver.stdout:
            first = ver.stdout.splitlines()[0].strip()
            caps.ffmpeg_version = first
    except (subprocess.TimeoutExpired, OSError):
        pass
    logger.info("scoring_caps: %s", caps.summary())
    return caps


__all__ = ["ScoringCapabilities", "detect"]
