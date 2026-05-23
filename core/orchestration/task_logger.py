"""Phase 3.4 — per-task ffmpeg log persistence + rotation.

Subscribes to the existing RenderWorker `output_updated` signal
(or any equivalent line-emitting source) and writes to
    USER_DATA_DIR/logs/<batch_uuid>/<task_uuid>.log

Caps each task log at 8 MB to prevent runaway disk growth on a
debug-level ffmpeg invocation. Rotates whole batch directories
on a manifest (`logs/index.json`) so the last N batches are
kept and older ones pruned at batch-complete time.

Pure-Python file I/O. No Qt, no ffmpeg. The Qt connection lives
in auto_render.py; this module only exposes the writer + the
rotation primitives.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("core.orchestration.task_logger")

LOGS_DIRNAME = "logs"
LOGS_INDEX_FILENAME = "index.json"
LOG_INDEX_SCHEMA_VERSION = 1

DEFAULT_MAX_BYTES_PER_TASK = 8 * 1024 * 1024  # 8 MB


class TaskLogger:
    """Per-batch log writer + rotation manifest.

    Usage from auto_render:
        tl = TaskLogger(user_data_dir, retain_batches=5)
        tl.begin_batch(batch_uuid)
        # for each line emitted from RenderWorker output_updated:
        tl.append(task_uuid, line)
        # at batch finish:
        tl.end_batch()
    """

    def __init__(
        self,
        user_data_dir: Path,
        *,
        retain_batches: int = 5,
        max_bytes_per_task: int = DEFAULT_MAX_BYTES_PER_TASK,
    ):
        self._user_data_dir = Path(user_data_dir)
        self._logs_dir = self._user_data_dir / LOGS_DIRNAME
        self._retain = max(1, int(retain_batches))
        self._max_bytes = max(64 * 1024, int(max_bytes_per_task))
        self._batch_uuid: Optional[str] = None
        # task_uuid -> bytes written so far (cheap cap check)
        self._bytes_written: dict[str, int] = {}

    # ----- public surface -----

    def begin_batch(self, batch_uuid: str) -> None:
        """Start logging for a new batch."""
        self._batch_uuid = batch_uuid
        self._bytes_written.clear()
        try:
            (self._logs_dir / batch_uuid).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("task_logger: cannot mkdir for %s: %s", batch_uuid, exc)

    def append(self, task_uuid: str, line: str) -> None:
        """Write one line to <batch>/<task>.log. Honours the 8 MB cap."""
        if self._batch_uuid is None or not task_uuid:
            return
        try:
            written = self._bytes_written.get(task_uuid, 0)
            if written >= self._max_bytes:
                return  # silently drop further bytes for this task
            path = self._logs_dir / self._batch_uuid / f"{task_uuid}.log"
            data = (line if line.endswith("\n") else line + "\n").encode(
                "utf-8", errors="replace"
            )
            with open(path, "ab") as f:
                f.write(data)
            self._bytes_written[task_uuid] = written + len(data)
        except OSError as exc:
            logger.debug("task_logger: append failed: %s", exc)

    def end_batch(self) -> None:
        """Update the rotation manifest + prune old batches."""
        if self._batch_uuid is None:
            return
        self._update_manifest()
        self._prune()
        self._batch_uuid = None

    # ----- internals -----

    def _read_manifest(self) -> dict:
        path = self._logs_dir / LOGS_INDEX_FILENAME
        if not path.is_file():
            return {"schema_version": LOG_INDEX_SCHEMA_VERSION, "batches": []}
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": LOG_INDEX_SCHEMA_VERSION, "batches": []}
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != LOG_INDEX_SCHEMA_VERSION
        ):
            return {"schema_version": LOG_INDEX_SCHEMA_VERSION, "batches": []}
        return data

    def _write_manifest(self, data: dict) -> None:
        path = self._logs_dir / LOGS_INDEX_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("task_logger: manifest write failed: %s", exc)

    def _update_manifest(self) -> None:
        data = self._read_manifest()
        batches = data.get("batches") or []
        # de-dupe; latest at the end.
        batches = [b for b in batches if b.get("batch_uuid") != self._batch_uuid]
        batches.append({"batch_uuid": self._batch_uuid, "finished_at": time.time()})
        data["batches"] = batches
        self._write_manifest(data)

    def _prune(self) -> None:
        data = self._read_manifest()
        batches = data.get("batches") or []
        if len(batches) <= self._retain:
            return
        excess = batches[: len(batches) - self._retain]
        keep = batches[len(batches) - self._retain :]
        for entry in excess:
            uuid = entry.get("batch_uuid")
            if not uuid:
                continue
            target = self._logs_dir / uuid
            try:
                if target.is_dir():
                    shutil.rmtree(target)
            except OSError as exc:
                logger.debug("task_logger: prune failed for %s: %s", uuid, exc)
        data["batches"] = keep
        self._write_manifest(data)


__all__ = [
    "DEFAULT_MAX_BYTES_PER_TASK",
    "LOGS_DIRNAME",
    "LOGS_INDEX_FILENAME",
    "LOG_INDEX_SCHEMA_VERSION",
    "TaskLogger",
]
