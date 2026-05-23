"""Phase 3.2 — perceptual-hash distance runner (originality axis).

We use **dHash** (difference hash), not DCT pHash, for two reasons:

  1. No numpy / no scipy dependency. dHash is plain pixel
     comparison — resize to 9x8 grayscale, then for each row emit
     8 bits comparing column[i] > column[i+1]. 64-bit hash.
  2. Pillow already ships in requirements.txt (since Phase 2c-c),
     so adding Pillow's resize-and-grayscale path is free. DCT
     would have pulled numpy or a hand-rolled 32x32 DCT (~80 LOC of
     numeric code that needs its own tests).

Frame sampling: rather than decoding every frame of a long video,
we extract `n_frames` equally-spaced frames via:

    ffmpeg -ss <t> -i <input> -frames:v 1 -vf scale=144x128 \
           -f image2pipe -vcodec mjpeg -

per frame. This costs ~1 keyframe seek per frame (~50 ms each on
modern disks). For a 60 s clip with n=20 frames that's ~1 s per
file, or ~2 s total for the (reference, distorted) pair.

Hamming distance:
    per_frame_distance = bin(hash_ref XOR hash_dist).count("1")
    avg = mean over sampled frame pairs
    max = max over sampled frame pairs

Higher distance = more visually different = more "original". The
caller decides what bands to colour (suggested in the design doc:
0-5 = identical, 6-15 = light edit, 16-25 = heavy edit, 26+ =
fundamentally different).

Pure local Python. No network. The only filesystem write is the
optional ffmpeg JPEG pipe (in-memory, not a temp file).
"""

from __future__ import annotations

import io
import logging
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional

from core import ffmpeg_runner as core_ffmpeg_runner
from core.scoring.score_models import ScoreAxisStatus, ScoreResult

logger = logging.getLogger("core.scoring.phash_runner")

# Default sampling: 20 frames is enough to detect heavy filter changes
# without paying for full decode. The user can override via the
# n_frames kwarg if they want denser sampling.
DEFAULT_FRAMES = 20

# Resize target for dHash: 9 columns x 8 rows = 8 differences per
# row x 8 rows = 64 bits. This is the canonical dHash sizing.
_DHASH_W = 9
_DHASH_H = 8

# Resize target for the initial JPEG extract — slightly larger than
# 9x8 so the JPEG compression doesn't lose tiny details that affect
# the dHash. 144x128 keeps aspect ratio close to 16x14 (cheap to
# decode + grayscale).
_EXTRACT_W = 144
_EXTRACT_H = 128


def _stat_or_zero(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _probe_duration_seconds(ffmpeg_path: Path, video: Path) -> Optional[float]:
    """Best-effort duration probe via ffmpeg stderr. Returns None on failure.

    We deliberately avoid ffprobe here because the bundled ffmpeg
    on some build configurations does not ship ffprobe as a
    separate binary. ffmpeg's own -hide_banner -i parse of stderr
    "Duration: 00:00:30.50" line is universal.
    """
    try:
        proc = subprocess.run(
            [str(ffmpeg_path), "-hide_banner", "-i", str(video)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=core_ffmpeg_runner.hidden_creationflags(),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    haystack = (proc.stderr or "") + (proc.stdout or "")
    # Line example: "  Duration: 00:00:30.50, start: 0.000000, bitrate: ..."
    for line in haystack.splitlines():
        line = line.strip()
        if not line.startswith("Duration:"):
            continue
        rest = line[len("Duration:") :].strip().split(",", 1)[0].strip()
        if rest == "N/A":
            return None
        try:
            h, m, s = rest.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, AttributeError):
            return None
    return None


def _extract_frame_jpeg(
    ffmpeg_path: Path, video: Path, at_seconds: float, timeout_seconds: float = 15.0
) -> Optional[bytes]:
    """Extract a single JPEG frame at the given timestamp.

    Returns the JPEG bytes, or None on failure. Uses fast -ss seek
    BEFORE -i (keyframe seek; small accuracy loss vs after-input
    seek, but ~10x faster on long files).
    """
    cmd = [
        str(ffmpeg_path),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{at_seconds:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        f"scale={_EXTRACT_W}:{_EXTRACT_H}",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            creationflags=core_ffmpeg_runner.hidden_creationflags(),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("phash_runner: frame extract failed: %s", exc)
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def _dhash_64(jpeg_bytes: bytes) -> Optional[int]:
    """Compute the 64-bit dHash of a JPEG frame using Pillow.

    Returns None if Pillow can't decode the bytes (corrupt JPEG,
    truncated pipe). Pure-Python pixel comparison; no numpy.
    """
    try:
        # Import lazily so the module imports clean even if Pillow
        # is somehow missing from the runtime (e.g. stripped build).
        from PIL import Image
    except ImportError:
        logger.warning("phash_runner: Pillow not installed; pHash unavailable")
        return None
    try:
        img = Image.open(io.BytesIO(jpeg_bytes))
        # Pillow 9.1+ moved resampling constants to Image.Resampling;
        # the old top-level Image.LANCZOS still works through Pillow 13
        # but is deprecated. Prefer the new attribute when present.
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img = img.convert("L").resize((_DHASH_W, _DHASH_H), resample)
    except Exception as exc:
        logger.debug("phash_runner: PIL decode failed: %s", exc)
        return None
    # Convert to a row-major list of grayscale pixel values. Pillow
    # 13 emits a DeprecationWarning for img.getdata(); the future-safe
    # path is `bytes(img)` which gives the raw pixel buffer for "L"
    # mode (one byte per pixel). Available since Pillow 9 and stable
    # across the 12.x / 13.x bridge.
    pixels = list(img.tobytes())
    # 9 cols x 8 rows = 72 grayscale values. Row-major.
    bits = 0
    for row in range(_DHASH_H):
        row_offset = row * _DHASH_W
        for col in range(_DHASH_W - 1):
            left = pixels[row_offset + col]
            right = pixels[row_offset + col + 1]
            if left > right:
                bits = (bits << 1) | 1
            else:
                bits = bits << 1
    return bits


def _hamming64(a: int, b: int) -> int:
    """Population count of a XOR b. Stdlib only."""
    return bin(a ^ b).count("1")


def score_phash(
    ffmpeg_path: Path,
    reference: Path,
    distorted: Path,
    *,
    n_frames: int = DEFAULT_FRAMES,
    should_cancel: Optional[Callable[[], bool]] = None,
    base_result: Optional[ScoreResult] = None,
) -> ScoreResult:
    """Compute average + max dHash Hamming distance across sampled frames.

    Args:
        ffmpeg_path: bundled local ffmpeg.
        reference: source video.
        distorted: rendered output.
        n_frames: how many equally-spaced frames to compare. Default 20.
        should_cancel: optional cancel poll (checked between frames).
        base_result: optional ScoreResult to mutate (so VMAF/SSIM/PSNR
            results can be chained on the same row).

    Returns ScoreResult with phash_* fields populated. Never raises.
    """
    if base_result is None:
        result = ScoreResult(
            reference_path=str(reference),
            reference_mtime=_stat_or_zero(reference),
            distorted_path=str(distorted),
            distorted_mtime=_stat_or_zero(distorted),
            computed_at=time.time(),
        )
    else:
        result = base_result

    if not reference.is_file() or not distorted.is_file():
        result.phash_status = ScoreAxisStatus.ERROR
        result.phash_error = "reference or distorted file missing"
        return result
    if n_frames < 1:
        result.phash_status = ScoreAxisStatus.ERROR
        result.phash_error = "n_frames must be >= 1"
        return result

    result.phash_status = ScoreAxisStatus.RUNNING

    duration = _probe_duration_seconds(ffmpeg_path, reference)
    if duration is None or duration <= 0:
        # Fall back to a single mid-file sample; better than failing.
        sample_times = [0.0]
    else:
        # Spread n_frames over the middle ~96% of the clip to dodge
        # the title-card / fade-in / fade-out regions where every
        # frame is solid black and dHash collapses to zero.
        margin = duration * 0.02
        usable = max(duration - 2 * margin, 0.5)
        if n_frames == 1:
            sample_times = [margin + usable / 2.0]
        else:
            step = usable / (n_frames - 1)
            sample_times = [margin + step * i for i in range(n_frames)]

    distances: List[int] = []
    for i, t in enumerate(sample_times):
        if should_cancel is not None:
            try:
                if should_cancel():
                    result.phash_status = ScoreAxisStatus.CANCELLED
                    return result
            except Exception:
                pass
        ref_bytes = _extract_frame_jpeg(ffmpeg_path, reference, t)
        dist_bytes = _extract_frame_jpeg(ffmpeg_path, distorted, t)
        if ref_bytes is None or dist_bytes is None:
            logger.debug(
                "phash_runner: skipping frame %d (t=%.2f) — extract failed", i, t
            )
            continue
        ref_hash = _dhash_64(ref_bytes)
        dist_hash = _dhash_64(dist_bytes)
        if ref_hash is None or dist_hash is None:
            continue
        distances.append(_hamming64(ref_hash, dist_hash))

    if not distances:
        result.phash_status = ScoreAxisStatus.ERROR
        result.phash_error = (
            f"no frame pair was successfully decoded "
            f"(tried {len(sample_times)} samples)"
        )
        return result

    result.phash_avg_distance = sum(distances) / len(distances)
    result.phash_max_distance = max(distances)
    result.phash_frames_compared = len(distances)
    result.phash_status = ScoreAxisStatus.OK
    return result


__all__ = ["score_phash", "DEFAULT_FRAMES"]
