"""Phase 3.4 — local-only orchestration / performance layer.

Pure-Python additive layer around RenderWorker. The renderer's
class, signals, and process() method are unchanged. Phase 3.4
contributes a scheduler, retry policy, queue-state side file
(pause/resume), per-task ffmpeg logger, diagnostic bundle export,
sleep-inhibitor context manager, and a system monitor.

Local-only. No network. No RenderWorker change.
"""

from __future__ import annotations

from core.orchestration.diagnostic_bundle import export_diagnostic_zip
from core.orchestration.queue_state import QUEUE_STATE_FILENAME, QueueState
from core.orchestration.retry_policy import (
    RetryDecision,
    RetryPolicyConfig,
    decide_retry,
)
from core.orchestration.scheduler import (
    DurationScheduler,
    FIFOScheduler,
    ManualPriorityScheduler,
)
from core.orchestration.sleep_inhibitor import SleepInhibitor
from core.orchestration.system_monitor import SystemSample, sample_system
from core.orchestration.task_logger import LOGS_INDEX_FILENAME, TaskLogger

__all__ = [
    "LOGS_INDEX_FILENAME",
    "QUEUE_STATE_FILENAME",
    "DurationScheduler",
    "FIFOScheduler",
    "ManualPriorityScheduler",
    "QueueState",
    "RetryDecision",
    "RetryPolicyConfig",
    "SleepInhibitor",
    "SystemSample",
    "TaskLogger",
    "decide_retry",
    "export_diagnostic_zip",
    "sample_system",
]
