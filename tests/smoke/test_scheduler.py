"""Smoke tests for `core.orchestration.scheduler`. ADR-0003 narrow."""

from __future__ import annotations

from core.orchestration.scheduler import (
    DurationScheduler,
    FIFOScheduler,
    ManualPriorityScheduler,
    TaskInfo,
)


def test_fifo_returns_lowest_index_first():
    sch = FIFOScheduler()
    tasks = [TaskInfo(index=2), TaskInfo(index=0), TaskInfo(index=1)]
    assert sch.next_task_index(tasks) == 0


def test_fifo_skips_already_dispatched():
    sch = FIFOScheduler()
    tasks = [TaskInfo(index=0), TaskInfo(index=1), TaskInfo(index=2)]
    assert sch.next_task_index(tasks, already_dispatched=[0, 1]) == 2


def test_fifo_empty_returns_none():
    assert FIFOScheduler().next_task_index([]) is None


def test_duration_shortest_first():
    sch = DurationScheduler(shortest_first=True)
    tasks = [
        TaskInfo(index=0, estimated_duration_s=60),
        TaskInfo(index=1, estimated_duration_s=10),
        TaskInfo(index=2, estimated_duration_s=30),
    ]
    assert sch.next_task_index(tasks) == 1


def test_duration_longest_first():
    sch = DurationScheduler(shortest_first=False)
    tasks = [
        TaskInfo(index=0, estimated_duration_s=60),
        TaskInfo(index=1, estimated_duration_s=10),
    ]
    assert sch.next_task_index(tasks) == 0


def test_duration_unknown_sorts_last_under_shortest_first():
    sch = DurationScheduler(shortest_first=True)
    tasks = [
        TaskInfo(index=0, estimated_duration_s=None),
        TaskInfo(index=1, estimated_duration_s=10),
    ]
    assert sch.next_task_index(tasks) == 1


def test_manual_priority_high_first():
    sch = ManualPriorityScheduler()
    tasks = [
        TaskInfo(index=0, priority="low"),
        TaskInfo(index=1, priority="high"),
        TaskInfo(index=2, priority="normal"),
    ]
    assert sch.next_task_index(tasks) == 1


def test_manual_priority_fifo_within_band():
    sch = ManualPriorityScheduler()
    tasks = [
        TaskInfo(index=3, priority="high"),
        TaskInfo(index=1, priority="high"),
    ]
    assert sch.next_task_index(tasks) == 1


def test_all_dispatched_returns_none():
    sch = FIFOScheduler()
    tasks = [TaskInfo(index=0), TaskInfo(index=1)]
    assert sch.next_task_index(tasks, already_dispatched=[0, 1]) is None
