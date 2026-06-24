"""Smoke test: non-ASCII log messages round-trip through each app's utf-8 FileHandler.

Each app's ``_setup_file_logging`` attaches an absolute-path FileHandler to the
root logger. With ``encoding="utf-8"`` a non-ASCII filename in a log message no
longer raises a cp1252 UnicodeEncodeError on Windows. We drive the REAL helper
(monkeypatched resolver + tmp_path, same idiom as test_logging_userdata.py),
log a non-ASCII string, and assert it round-trips; the handler is removed from
the root logger afterward so it does not leak into other tests.

ADR-0003 narrow exception (deterministic, no GPU/ffmpeg/Qt event loop, single-purpose).
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

import auto_render  # noqa: E402
import cutter  # noqa: E402
import merge  # noqa: E402
import mixer  # noqa: E402

APPS = [
    pytest.param(auto_render, "video_renderer.log", id="auto_render"),
    pytest.param(cutter, "video_cutter.log", id="cutter"),
    pytest.param(merge, "video_merge.log", id="merge"),
    pytest.param(mixer, "video_mixer.log", id="mixer"),
]

_NON_ASCII = "Tệp: Đoạn phim — 北京.mp4"


@pytest.mark.parametrize("app, filename", APPS)
def test_non_ascii_log_message_roundtrips_utf8(app, filename, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "resolve_user_data_dir", lambda install_dir: tmp_path)
    log_path = app._setup_file_logging(tmp_path, filename)
    root = logging.getLogger()
    handler = next(
        h
        for h in root.handlers
        if isinstance(h, logging.FileHandler) and h.baseFilename == log_path
    )
    try:
        root.error(_NON_ASCII)  # must not raise UnicodeEncodeError
        handler.flush()
        with open(log_path, encoding="utf-8") as fh:
            assert _NON_ASCII in fh.read()
    finally:
        handler.close()
        root.removeHandler(handler)
