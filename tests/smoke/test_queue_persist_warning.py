"""Smoke test: #1 — silent queue-persistence write failures surface ONCE.

queue_store.save() propagates OSError (atomic_write flushes+fsyncs then
re-raises), so disk-full / permissions failures reach auto_render's write call
sites. Those never crash the render; without a signal, resume capability is lost
silently. _note_queue_persist_failure logs every failure but appends a single
user-visible warning per batch (latched), re-armed at batch start.

Pure-logic test of the helper on a stub host — no QApplication/ffmpeg/GPU.
ADR-0003 narrow exception (deterministic, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types  # noqa: E402

import auto_render  # noqa: E402


def _host():
    appended = []
    h = types.SimpleNamespace(
        _queue_persist_warned=False,
        output_text=types.SimpleNamespace(append=appended.append),
    )
    h._note_queue_persist_failure = types.MethodType(
        auto_render.VideoRendererTool._note_queue_persist_failure, h
    )
    return h, appended


def test_persist_failure_warns_once_per_batch():
    h, appended = _host()
    h._note_queue_persist_failure("snapshot save", OSError("disk full"))
    h._note_queue_persist_failure("status update", OSError("disk full"))
    h._note_queue_persist_failure("clear", OSError("disk full"))
    assert len(appended) == 1  # surfaced once, not once per write
    assert "resume may be unavailable" in appended[0]
    assert h._queue_persist_warned is True


def test_warning_rearms_after_batch_reset():
    h, appended = _host()
    h._note_queue_persist_failure("snapshot save", OSError("x"))
    assert len(appended) == 1
    h._queue_persist_warned = False  # start_render re-arms at batch start
    h._note_queue_persist_failure("snapshot save", OSError("x"))
    assert len(appended) == 2
