"""Smoke test: M-1 — a render thread that will not stop within the join
timeout is *parked* (its (thread, worker) pair retained) instead of having
its last reference dropped, which would abort the process with
"QThread: Destroyed while thread is still running". Parked pairs are released
once their thread reports stopped.

Pure-logic test of VideoRendererTool._join_render_thread / _reap_parked_threads:
both only touch self._parked_threads, so the methods are bound to a tiny stub
self and driven with a fake thread whose wait()/isRunning() we control. No
QApplication, ffmpeg, GPU, or Qt event loop — the fake's wait() returning False
reproduces the exact contract a real wedged QThread presents.

ADR-0003 narrow exception (deterministic, no GPU/ffmpeg/event-loop, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types  # noqa: E402

import auto_render  # noqa: E402


class _FakeSignal:
    def disconnect(self):
        raise TypeError


class _FakeThread:
    def __init__(self, *, stops: bool):
        self._stops = stops
        self._running = True
        self.started = _FakeSignal()
        self.quit_called = False

    def quit(self):
        self.quit_called = True
        if self._stops:
            self._running = False

    def wait(self, _ms):
        return self._stops

    def isRunning(self):
        return self._running


def _host():
    h = types.SimpleNamespace(_parked_threads=[])
    h._reap_parked_threads = types.MethodType(
        auto_render.VideoRendererTool._reap_parked_threads, h
    )
    h._join_render_thread = types.MethodType(
        auto_render.VideoRendererTool._join_render_thread, h
    )
    return h


def test_stuck_thread_is_parked_not_dropped():
    h = _host()
    thread = _FakeThread(stops=False)
    worker = object()
    h._join_render_thread(thread, worker, timeout_ms=1)
    assert thread.quit_called
    assert (thread, worker) in h._parked_threads
    assert len(h._parked_threads) == 1


def test_thread_that_stops_is_not_parked():
    h = _host()
    thread = _FakeThread(stops=True)
    h._join_render_thread(thread, object(), timeout_ms=1)
    assert thread.quit_called
    assert h._parked_threads == []


def test_reap_releases_parked_thread_once_stopped():
    h = _host()
    thread = _FakeThread(stops=False)
    h._join_render_thread(thread, object(), timeout_ms=1)
    assert len(h._parked_threads) == 1
    thread._running = False
    h._reap_parked_threads()
    assert h._parked_threads == []
