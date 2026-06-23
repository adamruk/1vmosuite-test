"""Smoke test: M-3 — worker rows track num_threads.

``_rebuild_worker_rows`` regenerates the worker-indexed UI (thread_bars /
thread_labels / _worker_state) to exactly the requested count, so it stays
aligned with render_threads/render_workers when num_threads changes. Raising
the count must add rows (no "invisible workers"); lowering must drop them (no
dead "Ready" rows); rebuilding resets per-worker state.

The Qt widget classes are stubbed (like the suite stubs run_ffmpeg), so the
real rebuild/teardown logic runs with no QApplication, widgets, or event loop —
which also avoids the PySide process-exit teardown segfault.

ADR-0003 narrow exception (deterministic, no GPU/ffmpeg/event-loop, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types  # noqa: E402

import auto_render  # noqa: E402


class _FakeWidget:
    def __init__(self, *a, **k):
        pass

    def setFixedWidth(self, *_):
        pass

    def setMinimumWidth(self, *_):
        pass

    def setAlignment(self, *_):
        pass

    def setParent(self, *_):
        pass

    def deleteLater(self):
        pass


class _FakeRow:  # QHBoxLayout stand-in (a row of widgets)
    def __init__(self, *a, **k):
        self._items = []

    def setSpacing(self, *_):
        pass

    def addWidget(self, w, *a, **k):
        self._items.append(w)

    def count(self):
        return len(self._items)

    def takeAt(self, i):
        w = self._items.pop(i)
        return types.SimpleNamespace(widget=lambda: w, layout=lambda: None)

    def deleteLater(self):
        pass


class _FakeVBox:  # thread_layout stand-in (rows added via addLayout)
    def __init__(self):
        self._items = []

    def addLayout(self, lay):
        self._items.append(lay)

    def count(self):
        return len(self._items)

    def takeAt(self, i):
        lay = self._items.pop(i)
        return types.SimpleNamespace(layout=lambda: lay, widget=lambda: None)


def _host(monkeypatch):
    monkeypatch.setattr(auto_render, "QHBoxLayout", _FakeRow)
    monkeypatch.setattr(auto_render, "QLabel", _FakeWidget)
    monkeypatch.setattr(auto_render, "QProgressBar", _FakeWidget)
    h = types.SimpleNamespace(
        thread_bars=[], thread_labels=[], _worker_state=[], thread_layout=_FakeVBox()
    )
    h._rebuild_worker_rows = types.MethodType(
        auto_render.VideoRendererTool._rebuild_worker_rows, h
    )
    return h


def _aligned(h, n: int) -> bool:
    return (
        len(h.thread_bars) == n
        and len(h.thread_labels) == n
        and len(h._worker_state) == n
        and h.thread_layout.count() == n
    )


def test_initial_build(monkeypatch):
    h = _host(monkeypatch)
    h._rebuild_worker_rows(3)
    assert _aligned(h, 3)


def test_raise_thread_count_adds_rows(monkeypatch):
    h = _host(monkeypatch)
    h._rebuild_worker_rows(3)
    h._rebuild_worker_rows(5)  # user raised num_threads before the next batch
    assert _aligned(h, 5)  # new workers get rows -> not invisible


def test_lower_thread_count_drops_rows(monkeypatch):
    h = _host(monkeypatch)
    h._rebuild_worker_rows(3)
    h._rebuild_worker_rows(2)  # user lowered num_threads
    assert _aligned(h, 2)  # stale rows removed -> no dead "Ready" rows


def test_rebuild_resets_worker_state(monkeypatch):
    h = _host(monkeypatch)
    h._rebuild_worker_rows(3)
    h._worker_state[1]["state"] = "running"
    h._rebuild_worker_rows(3)
    assert all(s["state"] == "idle" for s in h._worker_state)
