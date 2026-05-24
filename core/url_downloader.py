"""URL downloader module — wraps yt-dlp for batch video downloads.

Implementation choice: yt-dlp as a Python library with progress_hooks,
plus concurrent.futures.ThreadPoolExecutor for the batch. This is the
cleanest fit for batch + cancellation + per-thread progress as
recommended in URL_DOWNLOADER_SPEC.md.

Public surface:
- download_videos(...) -> list[DownloadResult]
- DownloadResult dataclass

Argument validation may raise (ValueError, FileNotFoundError,
PermissionError). All other failures — invalid URL, unsupported site,
auth wall, network error, postprocess failure — are reported on the
DownloadResult, never raised. Callers inspect .success / .error_type.

The yt-dlp import is lazy inside _download_one so that argument-
validation smoke tests do not require yt-dlp to be installed.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional


# macOS stabilization (Step 5): resolve the bundled ffmpeg directory so
# yt-dlp uses the same binary the renderer uses, not whatever brew /
# system ffmpeg happens to be in PATH. yt-dlp invokes ffmpeg as a
# subprocess for muxing (merge_output_format=mp4) and subtitle remux;
# a mismatched system ffmpeg can produce containers the renderer
# rejects or codecs the bundled ffmpeg can't read.
#
# Resolution order:
#   1. PyInstaller frozen bundle:   sys._MEIPASS / "ffmpeg"
#   2. Source mode (Mac/Linux/Win): <repo_root> / "ffmpeg"
#   3. Fallback (no folder found):  None → yt-dlp uses PATH (legacy
#                                   behaviour; no regression on systems
#                                   that always relied on PATH ffmpeg).
def _resolve_bundled_ffmpeg_dir() -> Optional[str]:
    """Return the directory containing the bundled ffmpeg binary, or None.

    The path is passed to yt-dlp's `ffmpeg_location` option so the
    downloader and the renderer agree on which ffmpeg performs
    post-download muxing.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "ffmpeg")
    # Source-mode: this file lives at core/url_downloader.py, so the
    # repo root is the parent's parent.
    candidates.append(Path(__file__).resolve().parent.parent / "ffmpeg")
    suffix = ".exe" if os.name == "nt" else ""
    for cand in candidates:
        if (cand / f"ffmpeg{suffix}").is_file():
            return str(cand)
    return None


_BUNDLED_FFMPEG_DIR = _resolve_bundled_ffmpeg_dir()

logger = logging.getLogger("core.url_downloader")


def _resolve_bundled_js_runtime() -> Optional[str]:
    """Return the directory containing a bundled Deno binary, or None.

    Modern yt-dlp needs a JavaScript runtime (Deno) to solve the JS
    "n-sig"/PO-token challenges some extractors (notably YouTube) now
    require; without one those downloads degrade or fail. Mirrors
    _resolve_bundled_ffmpeg_dir: look in the PyInstaller bundle first,
    then the repo root. yt-dlp discovers the runtime via shutil.which,
    so the caller prepends this dir to PATH at import time.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    # Source-mode: repo root is this file's parent's parent.
    candidates.append(Path(__file__).resolve().parent.parent)
    suffix = ".exe" if os.name == "nt" else ""
    for cand in candidates:
        if (cand / f"deno{suffix}").is_file():
            return str(cand)
    return None


_BUNDLED_JS_RUNTIME_DIR = _resolve_bundled_js_runtime()
if _BUNDLED_JS_RUNTIME_DIR:
    # Prepend so yt-dlp's shutil.which finds the bundled Deno ahead of any
    # system install. Import-time so it is set before the first download.
    os.environ["PATH"] = (
        _BUNDLED_JS_RUNTIME_DIR + os.pathsep + os.environ.get("PATH", "")
    )
    logger.info("Bundled JS runtime (Deno) added to PATH: %s", _BUNDLED_JS_RUNTIME_DIR)


# ========== Quality format mapping ==========

# The download is a transient intermediate: it is ALWAYS re-encoded
# downstream by the NVENC renderer, never shipped as-is. So we optimise
# for source fidelity, not upload/playback compatibility — drop the
# [ext=mp4]/[ext=m4a] container pins and let yt-dlp pick the highest-
# quality video+audio streams regardless of container, muxed into mkv
# (see merge_output_format below). mkv accepts essentially any codec
# combination, so we never lose a better stream to a container mismatch.
QUALITY_FORMATS: dict[str, str] = {
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]",
    "720p": "bv*[height<=720]+ba/b[height<=720]",
    "480p": "bv*[height<=480]+ba/b[height<=480]",
    "360p": "bv*[height<=360]+ba/b[height<=360]",
    "smallest": "worst/w",
}


# ========== Internal exception hierarchy ==========


class URLDownloadError(Exception):
    """Base for internal categorized errors."""


class InvalidURLError(URLDownloadError):
    """URL is malformed, empty, a playlist, or a live stream."""


class UnsupportedSiteError(URLDownloadError):
    """yt-dlp does not support this site."""


class AuthRequiredError(URLDownloadError):
    """Auth required (private video, login wall)."""


class RegionLockedError(URLDownloadError):
    """Geo-blocked content."""


class RateLimitedError(URLDownloadError):
    """HTTP 429 / Cloudflare rate limit."""


class NetworkError(URLDownloadError):
    """Transient network/DNS/timeout error."""


class PostprocessError(URLDownloadError):
    """ffmpeg merge / remux failed."""


class _CancelledMarker(URLDownloadError):
    """Raised inside progress_hooks to abort yt-dlp on cancel_event."""


# ========== Public dataclass ==========


@dataclass
class DownloadResult:
    """Result of attempting to download a single URL within a batch.

    Always returned — never raises. Inspect .success to determine outcome.
    """

    url: str
    success: bool
    path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    error: Optional[Exception] = None
    error_type: Optional[str] = None
    title: Optional[str] = None
    duration_seconds: Optional[int] = None


# ========== Helpers ==========

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _validate_url(url: str) -> None:
    """Raise InvalidURLError on malformed / playlist / live stream URLs.

    Mixed watch+playlist URLs (e.g. youtube.com/watch?v=...&list=...) are
    accepted; yt-dlp's noplaylist=True will treat them as single videos.
    """
    if not isinstance(url, str) or not url.strip():
        raise InvalidURLError("Empty URL")
    stripped = url.strip()
    if not _URL_RE.match(stripped):
        raise InvalidURLError(f"Not a valid URL: {url!r}")
    lowered = stripped.lower()
    if "/playlist?" in lowered or "/playlist/" in lowered:
        raise InvalidURLError("Playlist URLs not supported, pass individual video URLs")
    if "/live/" in lowered:
        raise InvalidURLError("Live streams not supported")


def _categorize_error(exc: BaseException) -> str:
    """Translate an exception to one of the documented error_type strings."""
    if isinstance(exc, _CancelledMarker):
        return "cancelled"
    if isinstance(exc, InvalidURLError):
        return "invalid_url"
    if isinstance(exc, UnsupportedSiteError):
        return "unsupported_site"
    if isinstance(exc, AuthRequiredError):
        return "auth_required"
    if isinstance(exc, RegionLockedError):
        return "region_locked"
    if isinstance(exc, RateLimitedError):
        return "rate_limited"
    if isinstance(exc, NetworkError):
        return "network_error"
    if isinstance(exc, PostprocessError):
        return "postprocess_error"

    msg = str(exc).lower()

    if "no supported javascript runtime" in msg or "js runtime" in msg:
        return "js_runtime_missing"
    if "cookie" in msg and (
        "expired" in msg
        or "no longer valid" in msg
        or "malformed" in msg
        or "not a valid" in msg
        or "could not be loaded" in msg
        or "invalid" in msg
    ):
        return "cookies_invalid"
    if "unsupported url" in msg or "no suitable extractor" in msg:
        return "unsupported_site"
    if (
        "login required" in msg
        or "sign in" in msg
        or "private video" in msg
        or "this video is private" in msg
        or ("cookies" in msg and "auth" in msg)
    ):
        return "auth_required"
    if (
        "not available in your country" in msg
        or "geo restrict" in msg
        or ("geo" in msg and "block" in msg)
        or ("region" in msg and "restrict" in msg)
    ):
        return "region_locked"
    if (
        "http error 429" in msg
        or "rate limit" in msg
        or "too many requests" in msg
        or "cloudflare" in msg
    ):
        return "rate_limited"
    if any(
        s in msg
        for s in (
            "timeout",
            "timed out",
            "getaddrinfo",
            "name or service not known",
            "connection reset",
            "connection refused",
            "network is unreachable",
            "temporary failure in name resolution",
            "unable to download webpage",
        )
    ):
        return "network_error"
    if "ffmpeg" in msg and ("merge" in msg or "postprocess" in msg or "remux" in msg):
        return "postprocess_error"
    if "is not a valid url" in msg:
        return "invalid_url"

    return "unknown"


def _build_ydl_opts(
    quality: str,
    work_dir: Path,
    temp_dir: Path,
    download_subtitles: bool,
    subtitle_langs: list[str],
    cookies_file: Optional[Path],
    progress_hook: Callable[[dict], None],
) -> dict:
    """Build the yt-dlp options dict for a single download."""
    opts: dict = {
        "format": QUALITY_FORMATS[quality],
        "outtmpl": str(work_dir / "%(title).100B-%(id)s.%(ext)s"),
        # Isolate this download's partial/fragment files in a per-URL temp
        # dir so a cancel/crash leaves nothing in work_dir; the finished
        # file still lands in work_dir ("home"). _download_one rmtrees the
        # temp dir in a finally after the YoutubeDL instance closes.
        "paths": {"home": str(work_dir), "temp": str(temp_dir)},
        "restrict_filenames": True,
        # mkv intermediate: the renderer always re-encodes the download, so
        # we prefer a container that accepts any codec combo over one that
        # is upload-friendly. Avoids "incompatible codec for mp4" mux errors.
        "merge_output_format": "mkv",
        "noplaylist": True,
        "quiet": True,
        # Phase 2d production-hardening fix (Issue 6): silence yt-dlp's
        # own progress text to stderr. We already pipe per-URL progress
        # to the renderer via `progress_hooks`; yt-dlp's default stderr
        # progress is duplicative and pollutes the console + terminal
        # output panel.
        "noprogress": True,
        # Route yt-dlp's own log/warning/error output through our logger
        # (instead of suppressing it) so signals like "No supported JS
        # runtime" — see _resolve_bundled_js_runtime / "js_runtime_missing"
        # — are visible in logs rather than silently swallowed. We do NOT
        # set no_warnings (it would re-hide exactly those warnings).
        "logger": logger,
        "retries": 3,
        # macOS stabilization (Step 5): pin yt-dlp's muxer to the
        # bundled ffmpeg. On macOS source-mode the user may have
        # multiple ffmpeg builds in PATH (homebrew, MacPorts, system);
        # on frozen .app bundles PATH may not contain ffmpeg at all.
        # If we have a bundled binary, force yt-dlp to use it so the
        # renderer downstream sees the same codec / container support.
        # If no bundled ffmpeg is found, fall back to yt-dlp's default
        # PATH lookup (legacy behaviour).
        **({"ffmpeg_location": _BUNDLED_FFMPEG_DIR} if _BUNDLED_FFMPEG_DIR else {}),
        "fragment_retries": 3,
        "retry_sleep_functions": {
            "http": lambda n: 2**n,
            "fragment": lambda n: 2**n,
        },
        "progress_hooks": [progress_hook],
    }
    if download_subtitles:
        opts.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": list(subtitle_langs),
                "subtitlesformat": "srt/vtt/best",
                "postprocessors": [
                    {
                        "key": "FFmpegSubtitlesConvertor",
                        "format": "srt",
                    }
                ],
            }
        )
    if cookies_file is not None:
        opts["cookiefile"] = str(cookies_file)
    return opts


def _download_one(
    url: str,
    url_index: int,
    work_dir: Path,
    quality: str,
    download_subtitles: bool,
    subtitle_langs: list[str],
    cookies_file: Optional[Path],
    progress_callback: Optional[Callable[[int, str, float, str], None]],
    cancel_event: Optional[threading.Event],
) -> DownloadResult:
    """Download a single URL. Never raises — always returns a Result."""
    if cancel_event is not None and cancel_event.is_set():
        return DownloadResult(
            url=url,
            success=False,
            error_type="cancelled",
            error=_CancelledMarker("Cancelled before start"),
        )

    try:
        _validate_url(url)
    except InvalidURLError as exc:
        logger.error("Invalid URL %r: %s", url, exc)
        return DownloadResult(
            url=url, success=False, error=exc, error_type="invalid_url"
        )

    try:
        import yt_dlp
    except ImportError as exc:
        logger.error("yt-dlp not installed: %s", exc)
        return DownloadResult(url=url, success=False, error=exc, error_type="unknown")

    def _hook(d: dict) -> None:
        # #5957 hardening: yt-dlp fires this hook on a tight loop from the
        # download thread, so the hot path stays trivial — dict key reads
        # plus a single division, then hand off to the caller's callback.
        # No formatting, logging, or allocation here. (The except branch
        # below only runs if the *caller's* callback raises — not hot path.)
        if cancel_event is not None and cancel_event.is_set():
            raise _CancelledMarker("cancelled")
        if progress_callback is None:
            return
        status = d.get("status", "")
        try:
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = (downloaded / total * 100.0) if total else 0.0
                progress_callback(url_index, url, pct, "downloading")
            elif status == "finished":
                progress_callback(url_index, url, 100.0, "finished")
        except _CancelledMarker:
            raise
        except Exception:
            logger.exception("progress_callback raised; continuing")

    temp_dir = work_dir / f".ytdl_tmp_{url_index}"
    opts = _build_ydl_opts(
        quality,
        work_dir,
        temp_dir,
        download_subtitles,
        subtitle_langs,
        cookies_file,
        _hook,
    )
    logger.info("Starting download: %s", url)

    # The temp dir is rmtree'd in the finally — but only AFTER the
    # `with yt_dlp.YoutubeDL(...)` block exits. yt-dlp holds the .part /
    # fragment handles open until the YoutubeDL instance closes, so
    # cleaning up earlier (e.g. inside the progress hook) would race the
    # still-open handles on Windows. finally covers success, error, and
    # cancel alike.
    try:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = Path(ydl.prepare_filename(info))
        except _CancelledMarker as exc:
            return DownloadResult(
                url=url, success=False, error=exc, error_type="cancelled"
            )
        except Exception as exc:
            # Unwrap yt-dlp DownloadError if its cause is a _CancelledMarker
            if isinstance(
                getattr(exc, "__cause__", None), _CancelledMarker
            ) or isinstance(getattr(exc, "__context__", None), _CancelledMarker):
                return DownloadResult(
                    url=url, success=False, error=exc, error_type="cancelled"
                )
            error_type = _categorize_error(exc)
            logger.error("Download failed (%s): %s — %s", error_type, url, exc)
            return DownloadResult(
                url=url, success=False, error=exc, error_type=error_type
            )

        actual_path = filename
        if not actual_path.exists():
            # prepare_filename predicts the pre-merge extension; after a
            # merge_output_format=mkv mux the real file may carry a different
            # suffix. Trust prepare_filename first, then fall back to an
            # extension-agnostic glob on the (glob-escaped) stem and take
            # whatever the muxer actually wrote. No container is preferred —
            # the intermediate is re-encoded downstream regardless.
            candidates = list(work_dir.glob(f"{glob.escape(filename.stem)}.*"))
            if candidates:
                actual_path = candidates[0]
            else:
                err = PostprocessError(
                    f"Output file missing after download: {filename}"
                )
                logger.error("%s", err)
                return DownloadResult(
                    url=url, success=False, error=err, error_type="postprocess_error"
                )

        sub_path: Optional[Path] = None
        if download_subtitles:
            for cand in sorted(work_dir.glob(f"{actual_path.stem}*.srt")):
                sub_path = cand
                break

        title: Optional[str] = None
        duration_seconds: Optional[int] = None
        if isinstance(info, dict):
            t = info.get("title")
            title = t if isinstance(t, str) else None
            dur = info.get("duration")
            duration_seconds = int(dur) if isinstance(dur, (int, float)) else None

        logger.info("Download complete: %s -> %s", url, actual_path)
        return DownloadResult(
            url=url,
            success=True,
            path=actual_path,
            subtitle_path=sub_path,
            title=title,
            duration_seconds=duration_seconds,
        )
    finally:
        # Isolated per-URL fragment dir — safe to remove wholesale. The
        # finished output already lives in work_dir ("home"), not here.
        shutil.rmtree(temp_dir, ignore_errors=True)


# ========== Public function ==========


def download_videos(
    urls: list[str],
    work_dir: Path,
    quality: Literal["best", "1080p", "720p", "480p", "360p", "smallest"] = "best",
    download_subtitles: bool = False,
    subtitle_langs: Optional[list[str]] = None,
    max_concurrent: int = 3,
    progress_callback: Optional[Callable[[int, str, float, str], None]] = None,
    cookies_file: Optional[Path] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[DownloadResult]:
    """Download a batch of video URLs concurrently.

    Returns one DownloadResult per input URL, in the same order as `urls`.
    Per-URL failures are reported on the Result; only argument validation
    raises (ValueError, FileNotFoundError, PermissionError). See
    URL_DOWNLOADER_SPEC.md for full semantics and the error_type taxonomy.

    cookies_file, when given, is passed to yt-dlp as `cookiefile` (a
    Netscape-format cookie jar) to access auth-walled content. The CALLER
    is responsible for obtaining the user's consent before supplying it:
    downloading auth-walled media may violate a platform's Terms of
    Service and can put the account whose cookies are used at risk.
    Consent UI is out of scope for this module.
    """
    if not isinstance(urls, list) or len(urls) == 0:
        raise ValueError("urls must be a non-empty list")
    for i, u in enumerate(urls):
        if not isinstance(u, str):
            raise ValueError(f"urls[{i}] is not a string: got {type(u).__name__}")
    if quality not in QUALITY_FORMATS:
        raise ValueError(
            f"invalid quality {quality!r}; must be one of {sorted(QUALITY_FORMATS)}"
        )
    # Default to English captions only; normalised here (not as a mutable
    # default arg) so callers and threads never share one list instance.
    if subtitle_langs is None:
        subtitle_langs = ["en"]
    if (
        not isinstance(max_concurrent, int)
        or isinstance(max_concurrent, bool)
        or max_concurrent < 1
    ):
        raise ValueError(f"max_concurrent must be an int >= 1, got {max_concurrent!r}")
    if cookies_file is not None:
        cookies_file = Path(cookies_file)
        if not cookies_file.is_file():
            raise FileNotFoundError(f"cookies_file does not exist: {cookies_file}")
        if not os.access(cookies_file, os.R_OK):
            raise PermissionError(f"cookies_file is not readable: {cookies_file}")

    if not isinstance(work_dir, Path):
        work_dir = Path(work_dir)
    if not work_dir.exists():
        raise FileNotFoundError(f"work_dir does not exist: {work_dir}")
    if not work_dir.is_dir():
        raise FileNotFoundError(f"work_dir is not a directory: {work_dir}")
    if not os.access(work_dir, os.W_OK):
        raise PermissionError(f"work_dir is not writable: {work_dir}")

    n = len(urls)
    results: list[Optional[DownloadResult]] = [None] * n
    workers = min(max_concurrent, n)

    logger.info(
        "Starting batch of %d URL(s) (max_concurrent=%d, quality=%s, subs=%s)",
        n,
        max_concurrent,
        quality,
        download_subtitles,
    )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                _download_one,
                url,
                idx,
                work_dir,
                quality,
                download_subtitles,
                subtitle_langs,
                cookies_file,
                progress_callback,
                cancel_event,
            ): idx
            for idx, url in enumerate(urls)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:
                logger.exception("Worker raised unexpectedly for %r", urls[idx])
                results[idx] = DownloadResult(
                    url=urls[idx],
                    success=False,
                    error=exc,
                    error_type=_categorize_error(exc),
                )

    succeeded = sum(1 for r in results if r and r.success)
    logger.info("Batch complete: %d/%d succeeded", succeeded, n)

    return [r for r in results if r is not None]
