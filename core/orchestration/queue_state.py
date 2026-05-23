"""Phase 3.4 — pause/resume + scheduler policy + per-task priority
side-state file.

NEW side file at `USER_DATA_DIR/queue_state.json`. Keeps the
Phase 3.1 `queue.json` schema FROZEN at v1 — Phase 3.4 adds its
new state to a separate file so a Phase-3.4-unaware build sees
queue.json unchanged.

Atomic write + schema-version reject + never-raises load,
mirroring core/queue_store.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.atomic_write import save_json_atomic

logger = logging.getLogger("core.orchestration.queue_state")

QUEUE_STATE_FILENAME = "queue_state.json"
QUEUE_STATE_SCHEMA_VERSION = 1


class QueueState(BaseModel):
    """Side-state for Phase 3.4.

    Fields:
        paused                  user has paused the current batch
        paused_at               epoch seconds when pause clicked
        scheduler_policy        "fifo" / "duration_asc" /
                                "duration_desc" / "manual_priority"
        per_task_priorities     map task_uuid → "low"/"normal"/"high"
        per_task_retry_count    map task_uuid → int (current attempt
                                count; used by retry policy)
        batch_retry_count       running tally for the active batch
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=QUEUE_STATE_SCHEMA_VERSION)
    paused: bool = False
    paused_at: Optional[float] = None
    scheduler_policy: str = "fifo"
    per_task_priorities: Dict[str, str] = Field(default_factory=dict)
    per_task_retry_count: Dict[str, int] = Field(default_factory=dict)
    batch_retry_count: int = 0


def load_queue_state(user_data_dir: Path) -> Optional[QueueState]:
    """Read queue_state.json. Returns None on missing / corrupt /
    schema-mismatch — never raises."""
    path = Path(user_data_dir) / QUEUE_STATE_FILENAME
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as exc:
        logger.warning("queue_state: cannot read: %s", exc)
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("queue_state: corrupt JSON: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != QUEUE_STATE_SCHEMA_VERSION:
        logger.warning(
            "queue_state: schema mismatch (file=%r, expected=%d)",
            data.get("schema_version"),
            QUEUE_STATE_SCHEMA_VERSION,
        )
        return None
    try:
        return QueueState.model_validate(data)
    except ValidationError as exc:
        logger.warning("queue_state: validation failed: %s", exc)
        return None


def save_queue_state(user_data_dir: Path, state: QueueState) -> None:
    """Atomically persist queue_state.json. Caller wraps in try/except."""
    path = Path(user_data_dir) / QUEUE_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json_atomic(path, state.model_dump(mode="json"))


def clear_queue_state(user_data_dir: Path) -> None:
    """Remove queue_state.json. Idempotent."""
    path = Path(user_data_dir) / QUEUE_STATE_FILENAME
    try:
        path.unlink(missing_ok=True)
        bak = path.with_suffix(path.suffix + ".bak")
        bak.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("queue_state: clear failed: %s", exc)


__all__ = [
    "QUEUE_STATE_FILENAME",
    "QUEUE_STATE_SCHEMA_VERSION",
    "QueueState",
    "clear_queue_state",
    "load_queue_state",
    "save_queue_state",
]
