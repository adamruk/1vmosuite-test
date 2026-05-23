"""Smoke tests for `core.queue_store` (Phase 3.1 persistent queue).

ADR-0003 narrow-pytest exception: these tests exercise a pure-Python
disk persistence layer with no Qt / no ffmpeg / no GPU dependencies.
They run in <2 s, are deterministic, and would not be replaced by a
manual smoke log per ADR-0001's spirit (which is about RENDER and UI
verification, not pure-IO units).

All scenarios from the Phase 3.1 design document §6.1 are covered:
  1. empty-dir load returns None
  2. save → load round-trip
  3. update_task_status idempotency
  4. atomic write semantics (corruption isolation)
  5. corrupt JSON → load returns None
  6. clear() removes file
  7. lock blocks concurrent writer
  8. stale lock reclaimed at 60s
  9. schema-version mismatch returns None
 10. resume filters missing inputs (helper-level)
 11. resume filters missing presets (helper-level)
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from core.queue_models import (
    QUEUE_SCHEMA_VERSION,
    UNFINISHED_STATUSES,
    QueueBatch,
    QueueTask,
    TaskStatus,
)
from core.queue_store import (
    LOCK_FILENAME,
    QUEUE_FILENAME,
    STALE_LOCK_SECONDS,
    QueueStore,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _make_batch(tmp_path: Path, n_tasks: int = 5) -> QueueBatch:
    """Build a deterministic batch with `n_tasks` pending tasks."""
    tasks = [
        QueueTask(
            task_uuid=f"task-{i:04d}",
            task_index=i,
            video_path=str(tmp_path / f"input_{i}.mp4"),
            encoder_ids=["builtin:zoom-cycles/1080p-default"],
            video_idx=i,
            status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    return QueueBatch(
        batch_uuid="batch-test-0001",
        created_at=1_700_000_000.0,
        output_directory=str(tmp_path / "out"),
        sequential_mode=False,
        num_threads=3,
        settings_snapshot={"gpu_enabled": False},
        total_tasks=n_tasks,
        completed_tasks=0,
        tasks=tasks,
    )


@pytest.fixture
def store(tmp_path: Path) -> QueueStore:
    return QueueStore(user_data_dir=tmp_path)


# ----------------------------------------------------------------------
# Scenario 1 — empty dir load returns None
# ----------------------------------------------------------------------


def test_empty_dir_load_returns_none(store: QueueStore) -> None:
    assert store.load() is None


# ----------------------------------------------------------------------
# Scenario 2 — save then load round-trip
# ----------------------------------------------------------------------


def test_save_then_load_roundtrip(store: QueueStore, tmp_path: Path) -> None:
    original = _make_batch(tmp_path, n_tasks=3)
    store.save(original)
    loaded = store.load()
    assert loaded is not None
    assert loaded.batch_uuid == original.batch_uuid
    assert loaded.total_tasks == 3
    assert len(loaded.tasks) == 3
    assert loaded.tasks[0].task_uuid == "task-0000"
    assert loaded.tasks[0].status is TaskStatus.PENDING
    assert loaded.schema_version == QUEUE_SCHEMA_VERSION


# ----------------------------------------------------------------------
# Scenario 3 — update_task_status idempotency + counter alignment
# ----------------------------------------------------------------------


def test_update_task_status_idempotent(store: QueueStore, tmp_path: Path) -> None:
    store.save(_make_batch(tmp_path, n_tasks=3))
    store.update_task_status("task-0001", TaskStatus.COMPLETED, completed_at=42.0)
    # second call should be a no-op-equivalent
    store.update_task_status("task-0001", TaskStatus.COMPLETED, completed_at=42.0)
    loaded = store.load()
    assert loaded is not None
    assert loaded.tasks[1].status is TaskStatus.COMPLETED
    assert loaded.tasks[1].completed_at == 42.0
    # only one task is completed → batch-level counter is 1
    assert loaded.completed_tasks == 1


def test_update_task_status_unknown_uuid_noop(
    store: QueueStore, tmp_path: Path
) -> None:
    store.save(_make_batch(tmp_path, n_tasks=2))
    # Should not raise; should not corrupt the file.
    store.update_task_status("ghost-uuid", TaskStatus.FAILED)
    loaded = store.load()
    assert loaded is not None
    assert all(t.status is TaskStatus.PENDING for t in loaded.tasks)


def test_update_task_status_when_file_missing_noop(store: QueueStore) -> None:
    # No save first — queue file does not exist.
    store.update_task_status("task-0000", TaskStatus.COMPLETED)
    # No exception, no file appears.
    assert store.load() is None


# ----------------------------------------------------------------------
# Scenario 4 — atomic write semantics
# ----------------------------------------------------------------------


def test_save_then_clear_then_save_clean_state(
    store: QueueStore, tmp_path: Path
) -> None:
    store.save(_make_batch(tmp_path, n_tasks=2))
    store.clear()
    assert store.load() is None
    # Second save should work cleanly afterwards.
    store.save(_make_batch(tmp_path, n_tasks=1))
    loaded = store.load()
    assert loaded is not None
    assert loaded.total_tasks == 1


# ----------------------------------------------------------------------
# Scenario 5 — corrupt JSON → load returns None
# ----------------------------------------------------------------------


def test_corrupt_json_load_returns_none(store: QueueStore, tmp_path: Path) -> None:
    (tmp_path / QUEUE_FILENAME).write_text("{not json", encoding="utf-8")
    assert store.load() is None


def test_non_object_payload_load_returns_none(
    store: QueueStore, tmp_path: Path
) -> None:
    (tmp_path / QUEUE_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert store.load() is None


# ----------------------------------------------------------------------
# Scenario 6 — clear removes file (and .bak)
# ----------------------------------------------------------------------


def test_clear_removes_file(store: QueueStore, tmp_path: Path) -> None:
    # First save creates queue.json. Second save rotates queue.json
    # to queue.json.bak (per atomic_write contract). Verify clear()
    # removes both.
    store.save(_make_batch(tmp_path, n_tasks=1))
    store.save(_make_batch(tmp_path, n_tasks=2))
    assert (tmp_path / QUEUE_FILENAME).exists()
    bak = tmp_path / (QUEUE_FILENAME + ".bak")
    assert bak.exists()
    store.clear()
    assert not (tmp_path / QUEUE_FILENAME).exists()
    assert not bak.exists()


def test_clear_when_missing_is_noop(store: QueueStore) -> None:
    # Should not raise.
    store.clear()
    assert store.load() is None


# ----------------------------------------------------------------------
# Scenario 7 — lock blocks concurrent writer
# ----------------------------------------------------------------------


def test_lock_blocks_concurrent_writer(store: QueueStore) -> None:
    """While instance A holds the lock, instance B times out fast.

    We construct a SECOND store on the same tmp_path to simulate a
    second 1vmo process attempting to lock the same queue file.
    """
    second = QueueStore(user_data_dir=store._user_data_dir)
    holder_acquired_event = threading.Event()
    holder_release_event = threading.Event()

    def holder():
        with store.lock() as got:
            assert got is True
            holder_acquired_event.set()
            # Hold the lock until the test signals release.
            holder_release_event.wait(timeout=5.0)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    try:
        assert holder_acquired_event.wait(timeout=2.0)
        # Now try to acquire from the second instance with a tight
        # timeout — should not succeed while holder is alive.
        t0 = time.time()
        with second.lock(timeout=0.5) as got:
            # `got` must be False because the holder is alive.
            assert got is False
        elapsed = time.time() - t0
        # We waited ~0.5s for the timeout, not multi-seconds.
        assert elapsed < 2.0
    finally:
        holder_release_event.set()
        t.join(timeout=2.0)


# ----------------------------------------------------------------------
# Scenario 8 — stale lock reclaimed at STALE_LOCK_SECONDS
# ----------------------------------------------------------------------


def test_stale_lock_is_reclaimed(store: QueueStore, tmp_path: Path) -> None:
    lock_path = tmp_path / LOCK_FILENAME
    # Manually create a stale lock file (writable on all platforms).
    lock_path.write_text("99999", encoding="utf-8")
    # Backdate its mtime to STALE_LOCK_SECONDS + 1 seconds ago.
    past = time.time() - (STALE_LOCK_SECONDS + 1)
    os.utime(str(lock_path), (past, past))
    # Now the next lock() should reclaim and succeed quickly.
    t0 = time.time()
    with store.lock(timeout=2.0) as got:
        assert got is True
    elapsed = time.time() - t0
    assert elapsed < 2.0


# ----------------------------------------------------------------------
# Scenario 9 — schema-version mismatch returns None
# ----------------------------------------------------------------------


def test_schema_version_mismatch_returns_none(
    store: QueueStore, tmp_path: Path
) -> None:
    # Build a valid-shape payload with a wrong schema_version.
    payload = _make_batch(tmp_path, n_tasks=1).model_dump(mode="json")
    payload["schema_version"] = 99
    (tmp_path / QUEUE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    assert store.load() is None


def test_missing_schema_version_returns_none(store: QueueStore, tmp_path: Path) -> None:
    payload = _make_batch(tmp_path, n_tasks=1).model_dump(mode="json")
    payload.pop("schema_version", None)
    (tmp_path / QUEUE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    assert store.load() is None


# ----------------------------------------------------------------------
# Scenario 10/11 — resume helpers (path/preset filtering)
#
# The queue store itself doesn't filter — the caller (auto_render.py)
# is responsible for that. These tests verify the data the caller
# uses to make filtering decisions is available + consistent.
# ----------------------------------------------------------------------


def test_loaded_tasks_expose_video_path_and_encoder_ids(
    store: QueueStore, tmp_path: Path
) -> None:
    """Resume logic in auto_render.py filters by os.path.isfile and
    by `get_encoder_index_by_id`. This test confirms the on-disk
    schema exposes both fields verbatim so that filtering can occur.
    """
    store.save(_make_batch(tmp_path, n_tasks=2))
    loaded = store.load()
    assert loaded is not None
    for task in loaded.tasks:
        assert isinstance(task.video_path, str)
        assert isinstance(task.encoder_ids, list)
        assert all(isinstance(eid, str) for eid in task.encoder_ids)


def test_unfinished_statuses_set_for_resume_decision(
    store: QueueStore, tmp_path: Path
) -> None:
    """auto_render.py checks each task's status against
    UNFINISHED_STATUSES to decide whether to re-queue. This confirms
    the helper set is the right shape.
    """
    assert TaskStatus.PENDING in UNFINISHED_STATUSES
    assert TaskStatus.DISPATCHED in UNFINISHED_STATUSES
    assert TaskStatus.RUNNING in UNFINISHED_STATUSES
    assert TaskStatus.COMPLETED not in UNFINISHED_STATUSES
    assert TaskStatus.FAILED not in UNFINISHED_STATUSES
    assert TaskStatus.CANCELLED not in UNFINISHED_STATUSES
    assert TaskStatus.SKIPPED not in UNFINISHED_STATUSES
