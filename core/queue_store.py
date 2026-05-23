"""Local persistent queue store for the auto_render app (Phase 3.1).

Local-first design (Adam clarification 2026-05-19):

  - No cloud queue, no server roundtrip, no account/login.
  - The single source of truth is one JSON file in the user's local
    `user_data_dir` (resolved by `core.user_data.resolve_user_data_dir`).
  - File lock prevents corruption when two 1vmo instances launch
    simultaneously; that's the only multi-instance concern.

Design crib from FastFlix `fastflix/ff_queue.py`:
  - `O_CREAT | O_EXCL` lock file alongside the queue file.
  - Stale-lock detection at 60 seconds.
  - Atomic write via tempfile + rename (reusing 1vmo's existing
    `core.atomic_write.save_json_atomic` helper rather than re-rolling).
  - In-process threading.Lock to make the file lock idempotent if a
    single process double-acquires (cannot happen today since all
    callers are on the Qt main thread, but cheap to keep).

NOT a port of FastFlix code — the algorithm + atomic-write pattern
were independently re-implemented to fit 1vmo's lifecycle and to
reuse existing primitives.

What this module guarantees:
  - load() never raises. Missing file → None. Corrupt JSON → None.
    Schema-version mismatch → None. The caller can always launch
    cleanly from a None.
  - save() is atomic. A crash mid-save leaves the previous canonical
    queue.json untouched (atomic_write writes to .tmp then renames).
  - update_task_status() persists a single status transition by
    rewriting the whole file. Queue is small (≤ a few hundred
    tasks); per-transition rewrite is cheap and keeps the file
    invariant trivial (one JSON object, one schema version).
  - clear() removes the queue file (idempotent — no-op if absent).
  - All operations swallow OSError on the FILE side and re-raise on
    SCHEMA side. Callers wrap each call in their own try/except so
    a disk-full state never crashes the renderer.

What this module does NOT do:
  - It does NOT mutate RenderWorker, the render pipeline, the ffmpeg
    invocation, GPU semaphore, cancel semantics, output_collision,
    or any other Phase 2d invariant.
  - It does NOT validate that referenced video_paths exist or that
    preset IDs resolve. The caller (auto_render.py) is responsible
    for filtering those before re-queuing on resume.

Thread-safety:
  - Designed for the Qt main thread only. Qt signals already serialise
    slot invocations, so all save/load/update calls happen on a single
    thread. The in-process threading.Lock + file lock are defence in
    depth, not the primary concurrency story.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from core.atomic_write import save_json_atomic
from core.queue_models import (
    QUEUE_SCHEMA_VERSION,
    QueueBatch,
    QueueTask,
    TaskStatus,
)

logger = logging.getLogger("core.queue_store")

# File names inside user_data_dir.
QUEUE_FILENAME = "queue.json"
LOCK_FILENAME = "queue.json.lock"

# Stale-lock threshold: if the lock file is older than this, assume
# the holder crashed and reclaim. FastFlix uses 60 s — same here.
STALE_LOCK_SECONDS = 60.0

# Default lock-acquire timeout. Generous because all callers are on
# the Qt main thread and any contention is a multi-instance scenario.
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0


class QueueStore:
    """Persists the auto_render batch + per-task status to disk.

    Public surface intentionally minimal:
        lock()                  - context manager (file + thread lock)
        save(batch)             - write the batch atomically
        load()                  - read; returns Optional[QueueBatch]
        clear()                 - remove the queue file
        update_task_status(...) - mutate one task and persist

    Construction:
        store = QueueStore(user_data_dir=Path("..."))
    """

    def __init__(self, user_data_dir: Path):
        # Caller (auto_render.py) is responsible for ensuring the
        # directory exists; resolve_or_die already mkdir's it.
        self._user_data_dir = Path(user_data_dir)
        self._queue_path = self._user_data_dir / QUEUE_FILENAME
        self._lock_path = self._user_data_dir / LOCK_FILENAME
        self._mem_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def lock(self, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS):
        """Acquire the queue file lock (file + in-process).

        Yields True on success, False on timeout. Callers proceed
        anyway on False — better to allow the (possibly racing) write
        than to block the renderer forever. The contract matches
        FastFlix's pattern.
        """
        start = time.time()
        acquired = False
        with self._mem_lock:
            while time.time() - start < timeout:
                try:
                    # O_CREAT | O_EXCL — atomic create-or-fail. The
                    # holder writes its PID into the file so a future
                    # diagnostician can identify the holder.
                    fd = os.open(
                        str(self._lock_path),
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    )
                    try:
                        os.write(fd, str(os.getpid()).encode("ascii"))
                    finally:
                        os.close(fd)
                    acquired = True
                    break
                except FileExistsError:
                    # Stale-lock check: if the file is older than
                    # STALE_LOCK_SECONDS, the previous holder probably
                    # crashed without releasing. Remove and retry.
                    try:
                        age = time.time() - self._lock_path.stat().st_mtime
                    except OSError:
                        # Lock file disappeared between exists+stat —
                        # benign race; loop and re-attempt the create.
                        continue
                    if age > STALE_LOCK_SECONDS:
                        logger.warning(
                            "queue_store: reclaiming stale lock (age=%.1fs)",
                            age,
                        )
                        try:
                            self._lock_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        continue
                    time.sleep(0.1)
                except OSError as exc:
                    # E.g. permission denied on the directory. Don't
                    # spin forever; record and let the caller proceed.
                    logger.warning("queue_store: lock error: %s", exc)
                    break

            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        self._lock_path.unlink(missing_ok=True)
                    except OSError:
                        # Already gone or transient FS issue — no-op.
                        pass

    def save(self, batch: QueueBatch) -> None:
        """Atomically persist the batch to disk.

        Raises on serialisation failure (programmer error: a non-JSON
        value snuck into the batch). Wraps caller in lock + atomic
        write. OSError during write propagates so the caller can
        decide to surface a warning.
        """
        # Coerce through the model to enforce the on-disk schema even
        # if a caller passed a hand-built dict.
        payload = batch.model_dump(mode="json")
        # Ensure user_data_dir exists — defensive; should already.
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        with self.lock():
            save_json_atomic(self._queue_path, payload)

    def load(self) -> Optional[QueueBatch]:
        """Read and validate the on-disk batch.

        Returns None for any of:
          - file missing (most common case on first launch)
          - file unreadable (PermissionError, locked by another writer)
          - JSON malformed (corruption)
          - schema_version mismatch
          - pydantic validation failure (fields missing or wrong type)

        Logs a single warning line for the corruption cases — never
        crashes. First-launch case logs nothing.
        """
        if not self._queue_path.is_file():
            return None
        try:
            with open(self._queue_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as exc:
            logger.warning("queue_store: cannot read queue file: %s", exc)
            return None

        import json

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("queue_store: queue file is corrupt: %s", exc)
            return None

        # Fast-path schema check BEFORE pydantic — lets us reject
        # incompatible files without paying the validation cost.
        if not isinstance(data, dict):
            logger.warning("queue_store: queue payload is not an object")
            return None
        sv = data.get("schema_version")
        if sv != QUEUE_SCHEMA_VERSION:
            logger.warning(
                "queue_store: schema version mismatch (file=%r, expected=%d); "
                "ignoring saved queue",
                sv,
                QUEUE_SCHEMA_VERSION,
            )
            return None

        try:
            return QueueBatch.model_validate(data)
        except ValidationError as exc:
            logger.warning("queue_store: queue validation failed: %s", exc)
            return None

    def clear(self) -> None:
        """Remove the queue file. Idempotent — silent if absent."""
        with self.lock():
            try:
                self._queue_path.unlink(missing_ok=True)
                # Also clear any stale .bak from the atomic-write
                # rotation (single-generation per atomic_write contract).
                bak = self._queue_path.with_suffix(self._queue_path.suffix + ".bak")
                bak.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("queue_store: clear() failed: %s", exc)

    def update_task_status(
        self,
        task_uuid: str,
        status: TaskStatus,
        *,
        started_at: Optional[float] = None,
        completed_at: Optional[float] = None,
        error_message: Optional[str] = None,
        final_output: Optional[str] = None,
    ) -> None:
        """Update one task's status + side fields and re-persist.

        No-op (with a debug log) if the queue file is gone or the
        task_uuid is not found — keeps the caller from special-casing
        the "lost the queue mid-batch" scenario.

        The whole file is rewritten because the queue is small and
        partial-record updates are not worth the complexity vs the
        atomicity guarantee of save_json_atomic.
        """
        batch = self.load()
        if batch is None:
            logger.debug("queue_store: update_task_status no-op (queue file gone)")
            return

        for task in batch.tasks:
            if task.task_uuid == task_uuid:
                task.status = status
                if started_at is not None:
                    task.started_at = started_at
                if completed_at is not None:
                    task.completed_at = completed_at
                if error_message is not None:
                    task.error_message = error_message
                if final_output is not None:
                    task.final_output = final_output
                # Keep the batch-level completed_tasks counter aligned
                # with how many tasks are terminal-completed. Failed /
                # cancelled / skipped do not increment this counter
                # (they're recorded per-task; the batch-level value
                # remains the "successful renders" tally).
                batch.completed_tasks = sum(
                    1 for t in batch.tasks if t.status is TaskStatus.COMPLETED
                )
                self.save(batch)
                return

        logger.debug(
            "queue_store: update_task_status no-op (unknown task_uuid=%s)",
            task_uuid,
        )


__all__ = [
    "QueueStore",
    "QueueBatch",
    "QueueTask",
    "TaskStatus",
    "QUEUE_SCHEMA_VERSION",
    "QUEUE_FILENAME",
    "STALE_LOCK_SECONDS",
]
