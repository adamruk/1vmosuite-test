"""Smoke tests: M-4 pause traps.

M-4b — resuming a paused batch must refill EVERY free render slot, not just
one; otherwise throughput collapses to serial until each completion re-triggers
the next dispatch. We drive ``_toggle_pause`` on a stub host and count
``_start_next_task`` calls.

M-4a — a pause flag persisted from a prior session must be clearable durably
(in memory AND on disk) so clicking Start does not leave a silently dead batch.
We exercise the real ``_set_paused`` against a tmp queue_state dir.

Both are pure-logic tests: the methods are bound to a tiny stub ``self`` so no
QApplication, ffmpeg, GPU, or render threads are exercised.

ADR-0003 narrow exception (deterministic, no GPU/ffmpeg/event-loop, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types  # noqa: E402

import auto_render  # noqa: E402


class _Output:
    def append(self, *_args):
        pass


def _toggle_host(*, is_paused: bool, num_threads: int = 3):
    """Stub carrying just what _toggle_pause touches; counts dispatches."""
    h = types.SimpleNamespace(
        is_paused=is_paused,
        is_rendering=True,
        num_threads=num_threads,
        output_text=_Output(),
        dispatches=0,
    )

    def fake_set_paused(paused):
        h.is_paused = paused
        return True

    h._set_paused = fake_set_paused
    h._start_next_task = lambda: setattr(h, "dispatches", h.dispatches + 1)
    h._toggle_pause = types.MethodType(auto_render.VideoRendererTool._toggle_pause, h)
    return h


def test_resume_refills_all_free_slots():
    # M-4b: paused -> resume should fan out to num_threads dispatches, not 1.
    h = _toggle_host(is_paused=True, num_threads=3)
    h._toggle_pause()
    assert h.is_paused is False
    assert h.dispatches == 3


def test_pause_does_not_dispatch():
    # Direction guard: unpaused -> pause must NOT dispatch anything.
    h = _toggle_host(is_paused=False, num_threads=3)
    h._toggle_pause()
    assert h.is_paused is True
    assert h.dispatches == 0


def test_set_paused_persists_and_clears(tmp_path):
    # M-4a mechanism: _set_paused writes through to queue_state and back.
    from core.orchestration.queue_state import load_queue_state

    h = types.SimpleNamespace(
        USER_DATA_DIR=str(tmp_path),
        pause_btn=types.SimpleNamespace(setText=lambda *_: None),
    )
    h._set_paused = types.MethodType(auto_render.VideoRendererTool._set_paused, h)

    assert h._set_paused(True) is True
    assert h.is_paused is True
    assert load_queue_state(str(tmp_path)).paused is True

    # The Start guard's clear path: durable, not just in-memory.
    assert h._set_paused(False) is True
    assert h.is_paused is False
    assert load_queue_state(str(tmp_path)).paused is False
