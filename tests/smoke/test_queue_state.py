"""Smoke tests for `core.orchestration.queue_state`. ADR-0003 narrow."""

from __future__ import annotations

import json
from pathlib import Path

from core.orchestration.queue_state import (
    QUEUE_STATE_FILENAME,
    QUEUE_STATE_SCHEMA_VERSION,
    QueueState,
    clear_queue_state,
    load_queue_state,
    save_queue_state,
)


def test_load_missing_returns_none(tmp_path: Path):
    assert load_queue_state(tmp_path) is None


def test_save_then_load_roundtrip(tmp_path: Path):
    s = QueueState(
        paused=True,
        paused_at=123.0,
        scheduler_policy="duration_asc",
        per_task_priorities={"u1": "high"},
        per_task_retry_count={"u1": 1},
        batch_retry_count=1,
    )
    save_queue_state(tmp_path, s)
    loaded = load_queue_state(tmp_path)
    assert loaded is not None
    assert loaded.paused is True
    assert loaded.scheduler_policy == "duration_asc"
    assert loaded.per_task_priorities == {"u1": "high"}


def test_corrupt_json_returns_none(tmp_path: Path):
    (tmp_path / QUEUE_STATE_FILENAME).write_text("{not json", "utf-8")
    assert load_queue_state(tmp_path) is None


def test_schema_mismatch_returns_none(tmp_path: Path):
    payload = {"schema_version": 99, "paused": True}
    (tmp_path / QUEUE_STATE_FILENAME).write_text(json.dumps(payload), "utf-8")
    assert load_queue_state(tmp_path) is None


def test_clear_removes_file(tmp_path: Path):
    save_queue_state(tmp_path, QueueState(paused=True))
    assert (tmp_path / QUEUE_STATE_FILENAME).is_file()
    clear_queue_state(tmp_path)
    assert not (tmp_path / QUEUE_STATE_FILENAME).is_file()


def test_default_state_is_unpaused():
    s = QueueState()
    assert s.paused is False
    assert s.scheduler_policy == "fifo"
    assert s.schema_version == QUEUE_STATE_SCHEMA_VERSION


def test_extra_field_rejected():
    import pytest

    with pytest.raises(Exception):
        QueueState(paused=False, bogus="bad")
