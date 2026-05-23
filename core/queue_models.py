"""Pydantic v2 models for the Phase 3.1 persistent queue store.

Local-first design (no cloud, no remote queue): every QueueBatch is
serialized to a single JSON file in the user's local user_data_dir
(see `core/user_data.py`). The models below are the on-disk schema
of that file.

Schema versioning is intentional from day 1: the `QueueBatch.schema_version`
field lets QueueStore.load() reject incompatible payloads cleanly
(returns None + logs a warning) so a future field addition does not
crash the app for users with a stale queue file on disk. See ADR-0006
for the same pattern in the preset library.

These models are deliberately small. RenderWorker is unchanged.
encoder_ids hold ADR-0006 preset IDs (post-Item-5), never display
names. Status is a string-enum so it round-trips JSON cleanly without
serialiser shenanigans.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Schema version of the on-disk queue file format.
# Bump when an incompatible change is made to QueueTask / QueueBatch.
QUEUE_SCHEMA_VERSION = 1


class TaskStatus(str, Enum):
    """Lifecycle status for a single task in a saved batch."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


# Statuses that represent "still owes work" — used by QueueStore.load()
# to decide whether a saved batch warrants a resume prompt.
UNFINISHED_STATUSES = frozenset(
    {TaskStatus.PENDING, TaskStatus.DISPATCHED, TaskStatus.RUNNING}
)


class QueueTask(BaseModel):
    """Per-task record in the saved batch."""

    model_config = ConfigDict(extra="forbid")

    task_uuid: str
    task_index: int
    video_path: str
    encoder_ids: list[str]
    video_idx: int
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    final_output: Optional[str] = None


class QueueBatch(BaseModel):
    """The full saved batch. Single root object in queue.json.

    Field order is deliberate: schema_version FIRST so a future
    incompatible-load can short-circuit on the first key without
    parsing the rest of the payload.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=QUEUE_SCHEMA_VERSION)
    batch_uuid: str
    created_at: float
    output_directory: str
    sequential_mode: bool
    num_threads: int
    settings_snapshot: dict = Field(default_factory=dict)
    total_tasks: int
    completed_tasks: int = 0
    tasks: list[QueueTask] = Field(default_factory=list)
