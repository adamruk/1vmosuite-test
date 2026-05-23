"""Phase 3.4 — pluggable task scheduler policies.

Pure functions. No I/O, no Qt. The auto_render dispatcher calls
the active scheduler's `next_task_index(state)` instead of using
bare `current_task_index += 1`. FIFO preserves today's behavior;
DurationScheduler reorders by estimated duration; ManualPriority
honours per-task priority labels.

Each scheduler is a small stateless object so it can be swapped
at Settings OK time without restarting the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence


@dataclass(frozen=True)
class TaskInfo:
    """Slice of a task the scheduler needs. Strictly read-only."""

    index: int
    estimated_duration_s: Optional[float] = None
    priority: str = "normal"  # "low" / "normal" / "high"


class Scheduler(Protocol):
    """Scheduler protocol — caller passes remaining tasks + already-
    dispatched indices and gets back the next index to dispatch.

    Implementations are stateless; ordering decisions are made
    fresh on each call so a config change mid-batch takes effect
    on the next dispatch.
    """

    def next_task_index(
        self,
        remaining: Sequence[TaskInfo],
        already_dispatched: Iterable[int] = (),
    ) -> Optional[int]: ...


class FIFOScheduler:
    """Default policy. Returns the lowest-index task not yet dispatched."""

    name = "fifo"

    def next_task_index(
        self,
        remaining: Sequence[TaskInfo],
        already_dispatched: Iterable[int] = (),
    ) -> Optional[int]:
        done = set(already_dispatched)
        # Sort by task index so dispatch order matches the user's
        # input ordering regardless of how `remaining` was assembled.
        ordered = sorted(remaining, key=lambda t: t.index)
        for t in ordered:
            if t.index not in done:
                return t.index
        return None


class DurationScheduler:
    """Sort by estimated duration. shortest_first=True by default.

    Tasks without a duration estimate sort last (we don't know if
    they're cheap or expensive — keep them at the back so the
    fast ones drain first).
    """

    def __init__(self, shortest_first: bool = True):
        self.shortest_first = bool(shortest_first)
        self.name = "duration_asc" if shortest_first else "duration_desc"

    def next_task_index(
        self,
        remaining: Sequence[TaskInfo],
        already_dispatched: Iterable[int] = (),
    ) -> Optional[int]:
        done = set(already_dispatched)
        candidates = [t for t in remaining if t.index not in done]
        if not candidates:
            return None

        def _key(t: TaskInfo) -> tuple:
            # tasks with no estimate get sentinel +inf so they
            # sort last under shortest_first; vice versa for
            # longest_first.
            if t.estimated_duration_s is None:
                bucket = float("inf") if self.shortest_first else float("-inf")
            else:
                bucket = float(t.estimated_duration_s)
            return (bucket, t.index)

        candidates.sort(key=_key, reverse=not self.shortest_first)
        return candidates[0].index


class ManualPriorityScheduler:
    """Honour per-task priority labels. high → normal → low; FIFO inside each band."""

    name = "manual_priority"

    _ORDER = {"high": 0, "normal": 1, "low": 2}

    def next_task_index(
        self,
        remaining: Sequence[TaskInfo],
        already_dispatched: Iterable[int] = (),
    ) -> Optional[int]:
        done = set(already_dispatched)
        candidates = [t for t in remaining if t.index not in done]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (self._ORDER.get(t.priority, 1), t.index))
        return candidates[0].index


__all__ = [
    "DurationScheduler",
    "FIFOScheduler",
    "ManualPriorityScheduler",
    "Scheduler",
    "TaskInfo",
]
