# URL Downloader Module Spec

**Module:** `core/url_downloader.py`
**Owner:** Junaid (implementation), Adam (integration into auto_render.py — separate work)
**Status:** Spec — not yet implemented
**Phase:** Phase A (parallel with Adam's Phase 2 stabilization)

---

## Quick Reference

```python
download_videos(
    urls: list[str],
    work_dir: Path,
    quality: 'best' | '1080p' | '720p' | '480p' | '360p' | 'smallest' = 'best',
    download_subtitles: bool = False,
    max_concurrent: int = 3,
    progress_callback: Optional[Callable[[int, str, float, str], None]] = None,
    cookies_browser: Optional[str] = None,    # 'chrome' / 'firefox' / 'edge' / 'brave' / 'safari'
    cancel_event: Optional[threading.Event] = None,
) -> list[DownloadResult]
```

- Batch interface: list of URLs in, list of `DownloadResult` objects out
- Concurrent downloads (default 3 workers, configurable)
- Watermark-free by default (TikTok, Instagram, Facebook, etc.)
- Per-URL failures NEVER raise — they return as `DownloadResult(success=False, error_type=...)`
- Only argument validation can raise (`ValueError`, `FileNotFoundError`, `PermissionError`)
- Cross-platform: Windows + Apple Silicon Mac

**Files you create:**
- `core/url_downloader.py` (the module)
- `tests/smoke/test_url_downloader.py` (smoke tests)
- `requirements.txt` (add `yt-dlp>=2025.06.09`)

**Files you must NOT touch:** anything else in the repo.

---

## What this module does

Takes a list of video URLs, downloads them concurrently, returns per-URL results.

The downloaded files become input to the existing 1vmo render pipeline. **Integration into `auto_render.py` is NOT part of your scope** — that's Adam's work after this module ships.

---

## Public interface

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Literal
import threading


@dataclass
class DownloadResult:
    """Result of attempting to download a single URL within a batch.
    Always returned — never raises. Inspect .success to determine outcome."""
    url: str                                 # original URL passed in
    success: bool
    path: Optional[Path] = None              # set if success: video file path
    subtitle_path: Optional[Path] = None     # set if success AND subs requested AND available
    error: Optional[Exception] = None        # set if not success: original exception
    error_type: Optional[str] = None         # categorical label, see error_type values below
    title: Optional[str] = None              # video title from metadata, if extracted
    duration_seconds: Optional[int] = None   # video duration from metadata, if extracted


def download_videos(
    urls: list[str],
    work_dir: Path,
    quality: Literal['best', '1080p', '720p', '480p', '360p', 'smallest'] = 'best',
    download_subtitles: bool = False,
    max_concurrent: int = 3,
    progress_callback: Optional[Callable[[int, str, float, str], None]] = None,
    cookies_browser: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[DownloadResult]:
    ...
```

**Parameter notes:**

- `urls`: list of source URLs. yt-dlp supports 1000+ sites natively (YouTube, TikTok, Instagram Reels, Facebook, Twitter/X, Reddit, direct MP4, etc.). Watermark-free by default for all.
- `work_dir`: directory for downloaded files. Must exist and be writable.
- `quality`: discrete preset, mapped to yt-dlp format selectors internally.
- `download_subtitles`: try human subs first, fallback to auto-generated. Lang priority: English then video's original. Format SRT. Silent skip if unavailable (no error).
- `max_concurrent`: thread pool size. Default 3 — server rate limits make values >5 risky.
- `progress_callback`: `(url_index, url, percent_in_0_to_100, status_text)`. Called from worker threads — caller handles thread-safe UI updates.
- `cookies_browser`: source cookies from this browser for auth-walled content.
- `cancel_event`: `threading.Event`. When set, in-flight downloads finish current chunk and return cancelled; queued downloads return cancelled without starting; completed Results retain `success=True`.

**`error_type` values:** `'invalid_url'`, `'unsupported_site'`, `'auth_required'`, `'region_locked'`, `'rate_limited'`, `'network_error'`, `'postprocess_error'`, `'cancelled'`, `'unknown'`.

**Raises (only on argument validation):**
- `ValueError`: empty `urls`, non-string element, invalid `quality`, `max_concurrent < 1`, unknown `cookies_browser`
- `FileNotFoundError`: `work_dir` doesn't exist
- `PermissionError`: `work_dir` not writable

---

## How integrators will use this (example)

This is what Adam's eventual `auto_render.py` integration will look like. **You don't write this code** — but knowing the calling pattern helps you design the function correctly.

```python
import threading
from pathlib import Path
from core.url_downloader import download_videos

# Set up
work_dir = Path("C:/temp/1vmo_downloads")
work_dir.mkdir(parents=True, exist_ok=True)
cancel = threading.Event()

# Progress wired to UI (Qt signal in real integration)
def on_progress(idx: int, url: str, pct: float, status: str):
    print(f"[{idx}] {pct:5.1f}% — {status}: {url[:50]}")

# Run the batch
results = download_videos(
    urls=[
        "https://youtube.com/shorts/abc123",
        "https://tiktok.com/@user/video/12345",
        "https://instagram.com/reel/xyz789",
    ],
    work_dir=work_dir,
    quality='720p',
    download_subtitles=False,
    max_concurrent=3,
    progress_callback=on_progress,
    cancel_event=cancel,
)

# Process results
for r in results:
    if r.success:
        print(f"OK: {r.path} ({r.title})")
    else:
        print(f"FAIL [{r.error_type}]: {r.url} — {r.error}")
```

---

## Implementation approach (your call)

**Recommended: yt-dlp as Python library with `progress_hooks`.** Use `yt_dlp.YoutubeDL` directly. Wire `progress_callback` to yt-dlp's `progress_hooks` option. Catch yt-dlp's exception types (mostly `yt_dlp.utils.DownloadError` with stringly-typed messages) and translate to `error_type` categories. Use `concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent)` for the batch.

This is the cleanest fit for batch + cancellation + per-thread progress.

**Alternatives if you prefer:**
- **yt-dlp as subprocess** — shell out to the CLI. Simpler dep management but fragile progress parsing and harder cancellation.
- **Hybrid** — library for downloads, subprocess for any auxiliary feature.

Document your choice in the module docstring with one-sentence reasoning. We're not religious about it — pick what you've made work before.

---

## Quality mapping

```python
QUALITY_FORMATS = {
    'best':     'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    '1080p':    'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
    '720p':     'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
    '480p':     'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]',
    '360p':     'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]',
    'smallest': 'worst[ext=mp4]/worst',
}
```

Each level prefers MP4 video + M4A audio (mux to MP4), falls back to best MP4 at the height cap, then best at any container.

Always set `merge_output_format: 'mp4'` so the final file is MP4 even if yt-dlp picks non-MP4 sources.

---

## File naming

```python
'outtmpl': str(work_dir / '%(title).100B-%(id)s.%(ext)s'),
'restrict_filenames': True,
```

- `%(title).100B` truncates title to 100 bytes (handles Unicode)
- `%(id)s` ensures uniqueness if same title appears twice
- `restrict_filenames: True` is essential — strips characters that break Windows paths

After download, get the actual output path via `yt_dlp.YoutubeDL.prepare_filename(info)` since the extension may differ from `.mp4` if remuxing happened.

---

## Subtitles

When `download_subtitles=True`:

```python
'writesubtitles': True,
'writeautomaticsub': True,           # auto-gen as fallback
'subtitleslangs': ['en', 'orig'],    # English then original
'subtitlesformat': 'srt/vtt/best',
'postprocessors': [{
    'key': 'FFmpegSubtitlesConvertor',
    'format': 'srt',
}],
```

After download, locate the `.srt` file alongside the video (matching basename) and set `DownloadResult.subtitle_path`. **If no subtitles are available, leave it `None` and still return `success=True`.** No error.

---

## Watermark policy

**All downloads MUST be watermark-free by default.** yt-dlp's defaults already do this for TikTok, Instagram, Facebook — it picks source streams without overlay watermarks. Don't configure yt-dlp to use watermarked formats.

If watermarks start appearing, that's a regression bug, not a feature.

---

## Cancellation behavior

`cancel_event` is a `threading.Event`. When set:

1. **In-flight downloads** — finish current fragment, exit, return `Result(success=False, error_type='cancelled')`. Use yt-dlp's `progress_hooks` to check `cancel_event.is_set()` and raise to abort.
2. **Queued (not yet started)** — when a worker slot frees up, check `cancel_event` first. If set, return cancelled Result without attempting download.
3. **Completed** — leave `success=True` Results untouched.

The function still returns the full list of Results, in input order, when all workers exit.

---

## Retry policy

Use yt-dlp's built-in retry for transient failures:

```python
'retries': 3,
'fragment_retries': 3,
'retry_sleep_functions': {
    'http': lambda n: 2 ** n,
    'fragment': lambda n: 2 ** n,
},
```

After 3 retries per URL, give up and return `success=False`.

**Don't retry on:** invalid URL, unsupported site, auth required, region locked, cancellation.

---

## Edge cases — MUST work

| Case | Expected |
|---|---|
| YouTube standard / Shorts | Downloads at requested quality |
| TikTok | Downloads watermark-free |
| Instagram Reel (public) | Downloads |
| Instagram Reel (auth-walled) | `error_type='auth_required'`. With `cookies_browser='chrome'`: succeeds if Chrome is logged in. |
| Facebook public, Twitter/X, Reddit | Downloads |
| Direct .mp4 URL | Downloads |
| Mixed-platform batch (5 URLs) | All run concurrently up to `max_concurrent`, each its own Result |
| Invalid URL ("not a url") | `error_type='invalid_url'`. Other URLs unaffected. |
| Empty URL string | `error_type='invalid_url'` |
| Unsupported site | `error_type='unsupported_site'` |
| Region-locked | `error_type='region_locked'` |
| HTTP 429 / Cloudflare | `error_type='rate_limited'` after retries exhausted |
| Network timeout / DNS fail | `error_type='network_error'` after retries exhausted |
| Disk full mid-download | `error_type='unknown'` with descriptive `error.args[0]` |
| Postprocess (ffmpeg merge) fails | `error_type='postprocess_error'` |
| Quality unavailable (e.g. 1080p requested, only 720p exists) | Best below cap. `'smallest'` with no streams below cap → lowest available. |
| `cancel_event.set()` mid-batch | In-flight: finish chunk → cancelled Result. Queued: cancelled Result without start. Completed: untouched. |
| Subtitle requested, none available | `success=True`, `subtitle_path=None`. No error. |
| Playlist URL | `error_type='invalid_url'` with message "Playlist URLs not supported, pass individual video URLs". Use `noplaylist: True`. |
| Live stream URL | `error_type='invalid_url'` with message "Live streams not supported" |

---

## Out of scope (don't implement)

- **Resume / partial download** — caller retries from scratch on failure
- **Audio-only extraction** — always download video
- **Manual subtitle editing** — subs are downloaded as-is
- **Per-URL different quality settings** — whole batch uses the same `quality`
- **Pause / resume mid-batch** — cancellation only
- **Playlist expansion** — reject playlist URLs
- **Live streams** — reject live URLs

---

## Module structure

Single-file module, target ~400 lines:

```
core/url_downloader.py
├── Module docstring (overview, your implementation choice, limitations)
├── Logger setup
├── Custom exception classes (URLDownloadError + 7 subclasses, used internally)
├── DownloadResult dataclass
├── QUALITY_FORMATS dict
├── Helpers:
│   ├── _validate_url(url) -> raises InvalidURLError
│   ├── _build_ydl_opts(quality, subs, cookies, hook) -> dict
│   ├── _categorize_error(exception) -> error_type str
│   └── _download_one(url, work_dir, opts, cancel_event) -> DownloadResult
└── download_videos(...)  # the public function
```

Single function, no classes for the public interface.

---

## Logging

```python
logger = logging.getLogger('core.url_downloader')
```

Levels:
- `DEBUG` — yt-dlp options, full URL, output filename
- `INFO` — each URL started/completed, batch summary
- `WARNING` — retries triggered, slow downloads, cookies fallback
- `ERROR` — failures (before storing in Result)

No custom handlers — let the integrator configure.

---

## Tests

Create `tests/smoke/test_url_downloader.py`. Use pytest. Mark online tests with `@pytest.mark.online` so they can be skipped.

**Example test patterns:**

```python
import pytest
import threading
from pathlib import Path
from core.url_downloader import download_videos, DownloadResult

# Offline test — argument validation
def test_empty_urls_raises():
    with pytest.raises(ValueError):
        download_videos([], Path("/tmp"))

def test_invalid_quality_raises():
    with pytest.raises(ValueError):
        download_videos(["https://example.com/v.mp4"], Path("/tmp"), quality='4k')

# Offline test — invalid URL becomes failed Result, not exception
def test_invalid_url_returns_failed_result(tmp_path):
    results = download_videos(["not a url"], tmp_path)
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == 'invalid_url'

# Offline test — cancellation before start
def test_pre_cancelled_batch_returns_all_cancelled(tmp_path):
    cancel = threading.Event()
    cancel.set()
    results = download_videos(
        ["https://youtube.com/watch?v=test1", "https://youtube.com/watch?v=test2"],
        tmp_path,
        cancel_event=cancel,
    )
    assert all(r.error_type == 'cancelled' for r in results)

# Online test — actual download
@pytest.mark.online
def test_youtube_short_downloads(tmp_path):
    results = download_videos(
        ["https://www.youtube.com/shorts/SHORT_ID_HERE"],
        tmp_path,
        quality='720p',
    )
    assert results[0].success
    assert results[0].path.exists()
    assert results[0].path.suffix == '.mp4'
```

**Minimum 12 smoke tests:**
1. Empty `urls` raises `ValueError`
2. Invalid URL string returns `error_type='invalid_url'`
3. Empty URL string returns `error_type='invalid_url'`
4. Playlist URL returns `error_type='invalid_url'`
5. Invalid quality raises `ValueError`
6. `max_concurrent=0` raises `ValueError`
7. Pre-set `cancel_event` returns all-cancelled
8. Result list ordering matches input ordering (3 URLs, mixed valid/invalid)
9. (Online) YouTube Shorts downloads at `quality='720p'`
10. (Online) TikTok downloads watermark-free
11. (Online) `download_subtitles=True` for video with English subs returns non-None `subtitle_path`
12. (Online) Mixed batch (1 valid YouTube, 1 invalid, 1 TikTok) returns 3 Results with correct success/failure mapping

Trust yt-dlp itself — test YOUR translation layer (URL validation, exception mapping, batch coordination, cancellation, callback wiring).

---

## Dependencies

Add to `requirements.txt`:

```
yt-dlp>=2025.06.09
```

Pin a recent stable version. yt-dlp updates frequently to handle site changes — Adam updates the pin periodically.

No other new deps. Use stdlib for everything else (`logging`, `pathlib`, `dataclasses`, `threading`, `concurrent.futures`).

---

## Cross-platform notes

Runs on:
- **Windows** (Adam): Python 3.13, bundled FFmpeg
- **Apple Silicon Mac** (you): Python 3.13, system FFmpeg 8.1 with VideoToolbox

Avoid platform-specific paths:
- Use `pathlib.Path`, never `os.path.join` with backslashes
- Use `subprocess` with `shell=False` if you shell out
- Don't hardcode `/tmp` (use `work_dir`)
- `restrict_filenames: True` handles Windows-unsafe characters

The module should pass tests on both platforms with no per-platform branching.

---

## What's explicitly OUT OF SCOPE

- **No Qt / UI code** — module is pure Python (post-Phase-2d the suite is on PySide6; the rule here is "no UI bindings at all in this module")
- **No `auto_render.py` modifications** — Adam handles integration
- **No changes to existing 1vmo files** — only new files + `requirements.txt`
- **No "while I'm in there" cleanup** — flag issues to Adam, don't fix
- **No QThread management** — internal threading is `concurrent.futures`; Qt wrapping is the integrator's job
- **No config file reading** — all inputs are function arguments
- **No global state** beyond the logger
- **No platform-specific code paths**

If you find yourself wanting to do any of these, **stop and ask Adam first**.

---

## Definition of done

The module is done when ALL true:

1. `core/url_downloader.py` with `download_videos()` matching the spec signature
2. `DownloadResult` dataclass with all documented fields
3. All 7 internal exception classes defined
4. All 6 quality levels mapped to format strings
5. Subtitle path implemented (silent skip when unavailable)
6. Cancellation works correctly (in-flight + queued + completed)
7. MUST-work edge cases manually verified on at least: 1 YouTube, 1 Shorts, 1 TikTok, 1 IG Reel, 1 invalid URL, 1 cancellation, 1 batch of 5
8. `tests/smoke/test_url_downloader.py` with the 12 minimum tests
9. Module docstring documents your implementation choice + any deviations
10. `requirements.txt` updated with yt-dlp
11. PR opened following the commit + review discipline in `AGENTS.md` §5–6 (Conventional Commits, one concern per commit; the PR description lists any BACKLOG/ROADMAP items it closes)
12. Verified on macOS (your env) — Adam verifies on Windows during PR review

---

## Questions

If anything is ambiguous, ask Adam BEFORE writing code. Better to clarify upfront than rebuild after a wrong assumption.

If yt-dlp options here are deprecated by the time you start, surface that — don't blindly use stale recommendations.
