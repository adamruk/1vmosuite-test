"""Smoke test: all four apps route file logging to an absolute per-user path
via ``core.user_data``, with a safe fallback (E2 / B-021 + B-024).

Each app defines a module-level ``_setup_file_logging(install_dir, filename)``
that attaches an absolute-path ``FileHandler`` to the root logger using the
NON-exiting ``resolve_user_data_dir`` resolver, falling back to ``install_dir``
on any error (logging is configured at import time, before any QApplication
exists, so it must never exit or raise).

These tests drive that helper directly with a ``tmp_path`` install dir and a
monkeypatched resolver, so the assertions never write to the real user data
dir and do not depend on import-time global state. They cover: (a) the handler
is attached at an ABSOLUTE path under the resolved dir ending in the expected
``<app>.log`` name, with the original format + INFO level preserved and
idempotent on re-call; and (b) the fallback path — if the resolver raises,
logging still initializes (handler present, no exception propagated).

ADR-0003 narrow exception: deterministic, no GPU/ffmpeg/Qt event loop,
single-purpose regression coverage for a fix with near-zero manual-smoke
catch-rate (a wrong log path is invisible until a teammate needs the log).
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

# (app module, expected log filename)
APPS = [
    pytest.param(auto_render, "video_renderer.log", id="auto_render"),
    pytest.param(cutter, "video_cutter.log", id="cutter"),
    pytest.param(merge, "video_merge.log", id="merge"),
    pytest.param(mixer, "video_mixer.log", id="mixer"),
]


def _handlers_for(path: str):
    """Root FileHandlers whose baseFilename equals the given absolute path."""
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.FileHandler) and h.baseFilename == path
    ]


def _cleanup(path: str) -> None:
    """Detach + close any handler this test attached at ``path``."""
    root = logging.getLogger()
    for h in _handlers_for(path):
        try:
            h.close()
        finally:
            root.removeHandler(h)


@pytest.mark.parametrize("app, filename", APPS)
def test_handler_is_absolute_under_user_dir(app, filename, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "resolve_user_data_dir", lambda install_dir: tmp_path)
    expected = os.path.abspath(str(tmp_path / filename))
    _cleanup(expected)  # ensure a clean slate for the idempotency assertion
    try:
        result = app._setup_file_logging(tmp_path, filename)
        assert result == expected

        handlers = _handlers_for(expected)
        assert handlers, "expected a FileHandler at the resolved per-user path"
        handler = handlers[0]
        # absolute path, not a bare relative name
        assert os.path.isabs(handler.baseFilename)
        assert handler.baseFilename.endswith(filename)

        # original format string + INFO level preserved (byte-fidelity, §5)
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
        assert " - INFO - msg" in handler.formatter.format(record)
        assert logging.getLogger().level == logging.INFO

        # idempotent: a second call adds no duplicate handler for the same file
        assert app._setup_file_logging(tmp_path, filename) == expected
        assert len(_handlers_for(expected)) == 1
    finally:
        _cleanup(expected)


@pytest.mark.parametrize("app, filename", APPS)
def test_fallback_when_resolver_raises(app, filename, tmp_path, monkeypatch):
    def boom(install_dir):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(app, "resolve_user_data_dir", boom)
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    expected = os.path.abspath(str(install_dir / filename))
    _cleanup(expected)
    try:
        # must not raise even though the resolver does
        result = app._setup_file_logging(install_dir, filename)
        assert result == expected, "should fall back to install_dir"

        handlers = _handlers_for(expected)
        assert handlers, "fallback handler should still be configured"
        assert os.path.isabs(handlers[0].baseFilename)
    finally:
        _cleanup(expected)
