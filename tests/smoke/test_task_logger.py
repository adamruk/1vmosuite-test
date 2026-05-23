"""Smoke tests for `core.orchestration.task_logger`. ADR-0003 narrow."""

from __future__ import annotations

import json
from pathlib import Path

from core.orchestration.task_logger import (
    LOGS_INDEX_FILENAME,
    TaskLogger,
)


def test_append_writes_line(tmp_path: Path):
    tl = TaskLogger(tmp_path, retain_batches=5)
    tl.begin_batch("b1")
    tl.append("t1", "hello world")
    tl.end_batch()
    log = tmp_path / "logs" / "b1" / "t1.log"
    assert log.is_file()
    assert "hello world" in log.read_text("utf-8")


def test_index_updated(tmp_path: Path):
    tl = TaskLogger(tmp_path, retain_batches=5)
    tl.begin_batch("b1")
    tl.append("t1", "x")
    tl.end_batch()
    idx = tmp_path / "logs" / LOGS_INDEX_FILENAME
    assert idx.is_file()
    data = json.loads(idx.read_text("utf-8"))
    assert any(b["batch_uuid"] == "b1" for b in data["batches"])


def test_rotation_keeps_last_n(tmp_path: Path):
    tl = TaskLogger(tmp_path, retain_batches=2)
    for i in range(4):
        tl.begin_batch(f"batch{i}")
        tl.append("t1", "x")
        tl.end_batch()
    dirs = sorted((tmp_path / "logs").iterdir())
    batch_dirs = [d.name for d in dirs if d.is_dir()]
    assert len(batch_dirs) == 2
    assert "batch0" not in batch_dirs
    assert "batch3" in batch_dirs


def test_bytes_cap_drops_overflow(tmp_path: Path):
    tl = TaskLogger(tmp_path, retain_batches=5, max_bytes_per_task=128 * 1024)
    tl.begin_batch("b1")
    big = "x" * 2000
    for _ in range(120):
        tl.append("t1", big)
    tl.end_batch()
    log = tmp_path / "logs" / "b1" / "t1.log"
    assert log.is_file()
    assert log.stat().st_size <= 200 * 1024  # bounded near the cap


def test_append_without_begin_is_noop(tmp_path: Path):
    tl = TaskLogger(tmp_path)
    # No begin_batch — must not raise.
    tl.append("t1", "anything")
    assert not (tmp_path / "logs").is_dir() or not list((tmp_path / "logs").iterdir())
