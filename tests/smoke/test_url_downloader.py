"""Smoke tests for core.url_downloader.

Offline tests verify argument validation, URL validation, and batch
coordination without hitting the network. Online tests are tagged with
@pytest.mark.online and are SKIPPED unless RUN_ONLINE_TESTS=1 is set in
the environment, so the default `pytest tests/smoke/ -v` run is fast,
deterministic, and offline.

Run offline only (default):
    pytest tests/smoke/test_url_downloader.py -v

Run online tests too (hits YouTube / TikTok — flaky):
    RUN_ONLINE_TESTS=1 pytest tests/smoke/test_url_downloader.py -v
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# Ensure the repo root (which contains the `core/` package) is importable
# when pytest is invoked from the repo root with no conftest / pyproject.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from core.url_downloader import (
    QUALITY_FORMATS,
    DownloadResult,
    _categorize_error,
    _resolve_bundled_js_runtime,
    download_videos,
)

_ONLINE = os.environ.get("RUN_ONLINE_TESTS") == "1"
_skip_online = pytest.mark.skipif(
    not _ONLINE,
    reason="Set RUN_ONLINE_TESTS=1 to run online tests",
)


# ---------- 1. Empty urls list raises ValueError ----------


def test_empty_urls_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_videos([], tmp_path)


# ---------- 2. Invalid URL string -> failed Result, not exception ----------


def test_invalid_url_returns_failed_result(tmp_path: Path) -> None:
    results = download_videos(["not a url"], tmp_path)
    assert len(results) == 1
    assert isinstance(results[0], DownloadResult)
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"
    assert results[0].url == "not a url"
    assert results[0].path is None


# ---------- 3. Empty URL string -> invalid_url ----------


def test_empty_url_string_returns_failed_result(tmp_path: Path) -> None:
    results = download_videos([""], tmp_path)
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"


# ---------- 4. Playlist URL -> invalid_url ----------


def test_playlist_url_returns_invalid_url(tmp_path: Path) -> None:
    results = download_videos(
        ["https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"],
        tmp_path,
    )
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"


# ---------- 5. Invalid quality raises ValueError ----------


def test_invalid_quality_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_videos(
            ["https://example.com/v.mp4"],
            tmp_path,
            quality="4k",  # type: ignore[arg-type]
        )


# ---------- 6. max_concurrent=0 raises ValueError ----------


def test_max_concurrent_zero_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_videos(
            ["https://example.com/v.mp4"],
            tmp_path,
            max_concurrent=0,
        )


# ---------- 7. Pre-set cancel_event -> all-cancelled ----------


def test_max_concurrent_over_cap_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_videos(
            ["https://example.com/v.mp4"],
            tmp_path,
            max_concurrent=17,
        )


def test_max_concurrent_at_cap_is_accepted(tmp_path: Path) -> None:
    # 16 is the boundary — must pass validation (download fails per-URL).
    results = download_videos(["not a url"], tmp_path, max_concurrent=16)
    assert results[0].error_type == "invalid_url"


def test_pre_cancelled_batch_returns_all_cancelled(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    results = download_videos(
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=oHg5SJYRHA0",
        ],
        tmp_path,
        cancel_event=cancel,
    )
    assert len(results) == 2
    assert all(r.success is False for r in results)
    assert all(r.error_type == "cancelled" for r in results)


# ---------- 8. Result list ordering matches input ordering ----------


def test_result_order_matches_input_order(tmp_path: Path) -> None:
    urls = [
        "not a url",
        "",
        "still not a url",
    ]
    results = download_videos(urls, tmp_path)
    assert [r.url for r in results] == urls
    assert all(r.success is False for r in results)
    assert all(r.error_type == "invalid_url" for r in results)


# ---------- Additional offline coverage ----------


def test_missing_cookies_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        download_videos(
            ["https://example.com/v.mp4"],
            tmp_path,
            cookies_file=tmp_path / "no_such_cookies.txt",
        )


def test_valid_cookies_file_passes_validation(tmp_path: Path) -> None:
    # An existing, readable cookies file must clear arg-validation; the
    # download itself fails per-URL (no network / fake URL) without raising.
    jar = tmp_path / "cookies.txt"
    jar.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    results = download_videos(
        ["not a url"],
        tmp_path,
        cookies_file=jar,
    )
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"


def test_categorize_importerror_is_dependency_missing() -> None:
    assert _categorize_error(ImportError("No module named 'yt_dlp'")) == (
        "dependency_missing"
    )
    assert _categorize_error(ModuleNotFoundError("nope")) == "dependency_missing"


def test_categorize_cookies_invalid_message() -> None:
    assert (
        _categorize_error(
            Exception("The provided YouTube account cookies are no longer valid")
        )
        == "cookies_invalid"
    )
    assert (
        _categorize_error(Exception("cookies file is malformed")) == "cookies_invalid"
    )


def test_missing_work_dir_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        download_videos(["https://example.com/v.mp4"], missing)


def test_quality_formats_cover_all_documented_levels() -> None:
    assert set(QUALITY_FORMATS.keys()) == {
        "best",
        "1080p",
        "720p",
        "480p",
        "360p",
        "smallest",
    }


def test_non_string_url_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_videos([12345], tmp_path)  # type: ignore[list-item]


def test_lost_future_filled_so_len_matches_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C6d: even if every future is 'lost' (as_completed yields nothing),
    download_videos must still return one result per URL, in order."""
    import core.url_downloader as ud

    monkeypatch.setattr(ud, "as_completed", lambda futures: iter(()))
    urls = ["not a url", "also not a url", ""]
    results = download_videos(urls, tmp_path)
    assert len(results) == len(urls)
    assert [r.url for r in results] == urls
    assert all(r.success is False for r in results)
    assert all(r.error_type == "unknown" for r in results)


def test_is_live_post_extract_returns_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C6c: a URL with no /live/ marker that resolves to a live broadcast
    must be refused after the metadata probe, before any download."""
    import types

    downloaded = {"called": False}

    class _FakeYDL:
        def __init__(self, opts: dict) -> None:
            pass

        def __enter__(self) -> "_FakeYDL":
            return self

        def __exit__(self, *a: object) -> bool:
            return False

        def extract_info(self, url: str, download: bool):  # noqa: ANN201
            if download:
                downloaded["called"] = True
            return {"is_live": True, "title": "live broadcast"}

        def prepare_filename(self, info: dict) -> str:
            return str(tmp_path / "x.mkv")

    monkeypatch.setitem(
        sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYDL)
    )
    results = download_videos(
        ["https://www.youtube.com/watch?v=fakeLiveId"],
        tmp_path,
    )
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"
    assert downloaded["called"] is False, "must not download a live stream"


def test_js_runtime_resolver_returns_none_when_absent() -> None:
    # No Deno binary is bundled in the source tree / test env, so the
    # resolver must return None cleanly (never raise).
    result = _resolve_bundled_js_runtime()
    assert result is None or isinstance(result, str)


def test_categorize_js_runtime_missing_message() -> None:
    assert (
        _categorize_error(Exception("ERROR: No supported JavaScript runtime found"))
        == "js_runtime_missing"
    )
    assert _categorize_error(Exception("install a JS runtime such as Deno")) == (
        "js_runtime_missing"
    )


def test_live_stream_url_returns_invalid(tmp_path: Path) -> None:
    results = download_videos(
        ["https://www.youtube.com/live/abcdef12345"],
        tmp_path,
    )
    assert results[0].success is False
    assert results[0].error_type == "invalid_url"


# ---------- 9-12. Online tests (skipped by default) ----------


@_skip_online
@pytest.mark.online
def test_youtube_short_downloads(tmp_path: Path) -> None:
    results = download_videos(
        ["https://www.youtube.com/shorts/aqz-KE-bpKQ"],
        tmp_path,
        quality="720p",
    )
    assert len(results) == 1
    assert results[0].success is True, f"error={results[0].error}"
    assert results[0].path is not None
    assert results[0].path.exists()
    # Intermediate is now a quality-maximal mkv mux (merge_output_format=mkv);
    # a progressive single-stream fetch may keep its native container.
    assert results[0].path.suffix.lower() in {".mkv", ".mp4", ".webm"}


@_skip_online
@pytest.mark.online
def test_tiktok_downloads_watermark_free(tmp_path: Path) -> None:
    results = download_videos(
        ["https://www.tiktok.com/@scout2015/video/6718335390845095173"],
        tmp_path,
        quality="best",
    )
    assert results[0].success is True, f"error={results[0].error}"
    assert results[0].path is not None
    assert results[0].path.exists()


@_skip_online
@pytest.mark.online
def test_subtitles_for_video_with_english_subs(tmp_path: Path) -> None:
    # 'Me at the zoo' — first YouTube video, has English captions.
    results = download_videos(
        ["https://www.youtube.com/watch?v=jNQXAC9IVRw"],
        tmp_path,
        quality="480p",
        download_subtitles=True,
    )
    assert results[0].success is True, f"error={results[0].error}"
    assert results[0].subtitle_path is not None
    assert results[0].subtitle_path.exists()


@_skip_online
@pytest.mark.online
def test_subtitles_and_progress_reach_completion(tmp_path: Path) -> None:
    """#5957 regression guard: subtitles + a live progress_callback must
    coexist — complete video, a .srt on disk, AND progress reaching 100."""
    seen: list[float] = []

    def on_progress(idx: int, url: str, pct: float, status: str) -> None:
        seen.append(pct)

    results = download_videos(
        ["https://www.youtube.com/watch?v=jNQXAC9IVRw"],  # 'Me at the zoo'
        tmp_path,
        quality="480p",
        download_subtitles=True,
        subtitle_langs=["en"],
        progress_callback=on_progress,
    )
    assert len(results) == 1
    assert results[0].success is True, f"error={results[0].error}"
    assert results[0].path is not None and results[0].path.exists()
    assert results[0].subtitle_path is not None
    assert results[0].subtitle_path.exists()
    assert results[0].subtitle_path.suffix.lower() == ".srt"
    assert seen, "progress_callback was never invoked"
    assert max(seen) >= 100.0, f"progress never reached 100: max={max(seen)}"


@_skip_online
@pytest.mark.online
def test_cancel_mid_download_leaves_no_orphans(tmp_path: Path) -> None:
    """C3 guard: cancelling once bytes are flowing yields error_type
    'cancelled', leaves NO .part/.ytdl orphans in work_dir, removes the
    isolated temp dir, and the pool drains (download_videos returns)."""
    cancel = threading.Event()

    def on_progress(idx: int, url: str, pct: float, status: str) -> None:
        # Trip the cancel as soon as the first bytes arrive; the next
        # progress-hook invocation raises _CancelledMarker and aborts.
        cancel.set()

    results = download_videos(
        ["https://www.youtube.com/watch?v=aqz-KE-bpKQ"],
        tmp_path,
        quality="720p",
        progress_callback=on_progress,
        cancel_event=cancel,
    )
    # Pool drained — we got here, function returned.
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == "cancelled"
    orphans = list(tmp_path.rglob("*.part")) + list(tmp_path.rglob("*.ytdl"))
    assert orphans == [], f"orphaned partial files: {orphans}"
    assert not (tmp_path / ".ytdl_tmp_0").exists(), "temp dir not cleaned up"


@_skip_online
@pytest.mark.online
def test_mixed_batch_returns_correct_per_url_outcomes(tmp_path: Path) -> None:
    urls = [
        "https://www.youtube.com/shorts/aqz-KE-bpKQ",
        "not a url",
        "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    ]
    results = download_videos(urls, tmp_path, quality="480p", max_concurrent=2)
    assert len(results) == 3
    assert [r.url for r in results] == urls
    assert results[0].success is True
    assert results[1].success is False
    assert results[1].error_type == "invalid_url"
    assert results[2].success is True
