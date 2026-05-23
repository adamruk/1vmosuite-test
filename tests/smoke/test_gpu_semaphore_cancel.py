"""Smoke test for cancellable GPU-semaphore acquire (B-032 fix-pass).

B-032: RenderWorker.process() acquired the NVENC semaphore with a bare
`QSemaphore.acquire()`. Under contention (all slots held) that call blocks
indefinitely and cannot observe a cancel request, so a queued render could
not be cancelled while waiting for a free NVENC session.

The fix introduces `auto_render._acquire_gpu_slot(semaphore, should_cancel)`,
a bounded `tryAcquire`-in-a-loop that polls `should_cancel()` between
attempts. These tests exercise that helper directly — no GPU, no ffmpeg, no
RenderWorker construction. Each test that could block runs the helper on a
daemon thread guarded by `join(timeout=...)` so a regression (re-introduced
blocking acquire) surfaces as a clean test failure, never a hung suite.

ADR-0003 narrow exception (deterministic-with-timeout, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading  # noqa: E402
import time  # noqa: E402

from PySide6.QtCore import QSemaphore  # noqa: E402

import auto_render  # noqa: E402


def test_acquire_gpu_slot_succeeds_when_slot_free():
    """A free slot is acquired immediately; caller owns it and must release."""
    sem = QSemaphore(1)
    assert auto_render._acquire_gpu_slot(sem, lambda: False) is True
    assert sem.available() == 0
    sem.release()


def test_acquire_gpu_slot_cancel_before_first_attempt():
    """Already cancelled on entry: returns False and acquires nothing."""
    sem = QSemaphore(1)
    assert auto_render._acquire_gpu_slot(sem, lambda: True) is False
    assert sem.available() == 1  # untouched


def test_acquire_gpu_slot_honors_cancel_under_contention():
    """The B-032 repro: with the semaphore exhausted, a cancel request issued
    while a worker is blocked waiting must break the wait. A bare acquire()
    would block forever and ignore the cancel.
    """
    sem = QSemaphore(1)
    sem.acquire()  # exhaust — no slots free; a waiter must block until cancel
    cancel = {"flag": False}
    result = {}

    def run():
        result["acquired"] = auto_render._acquire_gpu_slot(
            sem, lambda: cancel["flag"], poll_ms=50
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.2)
    assert t.is_alive(), "helper should still be waiting while contended"

    cancel["flag"] = True  # request cancel while the waiter is blocked
    t.join(timeout=3.0)

    assert not t.is_alive(), "acquire did not return after cancel (hang)"
    assert result["acquired"] is False
    assert sem.available() == 0  # never over-acquired; the holder still holds
