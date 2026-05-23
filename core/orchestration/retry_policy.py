"""Phase 3.4 — conservative retry policy.

Built on top of Phase 3.3's failure_classifier. Default behaviour
is STRICT OFF — `max_retries_per_task = 0` and `enabled = False`
means decide_retry() always returns NONE. The user must opt in
via Settings before any auto-retry happens.

Allow-list of retry-eligible Recommendation kinds is small and
explicit. Per-task and per-batch ceilings cap runaway retry loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.optimization.failure_classifier import classify_failure
from core.optimization.recommendation_models import RecommendationKind

# Only these kinds are auto-retry candidates. Everything else (e.g.
# DEBUG_LOG for "no such file", UNKNOWN) requires manual review.
_RETRY_ELIGIBLE = frozenset(
    {RecommendationKind.RETRY_AS_IS, RecommendationKind.USE_CPU}
)

# Exponential backoff steps in seconds.
_BACKOFF_STEPS = (5.0, 30.0, 300.0)


class RetryAction(str, Enum):
    NONE = "none"
    RETRY_NOW = "retry_now"
    RETRY_LATER = "retry_later"


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction = RetryAction.NONE
    delay_seconds: float = 0.0
    reason: str = ""
    suggested_params: dict = None  # type: ignore[assignment]


@dataclass
class RetryPolicyConfig:
    """Settings → Orchestration knobs.

    Strict defaults: enabled=False AND max_retries_per_task=0
    means decide_retry() always returns NONE.
    """

    enabled: bool = False
    max_retries_per_task: int = 0
    max_retries_per_batch: int = 5


def decide_retry(
    error_message: Optional[str],
    *,
    task_retry_count: int,
    batch_retry_count: int,
    config: Optional[RetryPolicyConfig] = None,
) -> RetryDecision:
    """Decide whether to auto-retry a failed task.

    Returns NONE unless:
        - config.enabled is True
        - task_retry_count < config.max_retries_per_task
        - batch_retry_count < config.max_retries_per_batch
        - the error_message classifies into a retry-eligible Kind

    The Recommendation from classify_failure carries the
    suggested_params to apply on retry (e.g. gpu_enabled=False
    for an NVENC out-of-sessions error).
    """
    cfg = config or RetryPolicyConfig()
    if not cfg.enabled:
        return RetryDecision(reason="auto-retry disabled in settings")
    if cfg.max_retries_per_task <= 0:
        return RetryDecision(reason="max_retries_per_task is 0")
    if task_retry_count >= cfg.max_retries_per_task:
        return RetryDecision(reason=f"task already retried {task_retry_count} time(s)")
    if batch_retry_count >= cfg.max_retries_per_batch:
        return RetryDecision(reason="batch retry budget exhausted")

    rec = classify_failure(error_message)
    if rec.kind not in _RETRY_ELIGIBLE:
        return RetryDecision(
            reason=f"error kind {rec.kind.value} is not retry-eligible"
        )

    # Pick a backoff step. Defensive — we never let the index
    # exceed the table length.
    idx = min(max(task_retry_count, 0), len(_BACKOFF_STEPS) - 1)
    delay = _BACKOFF_STEPS[idx]
    return RetryDecision(
        action=RetryAction.RETRY_LATER if delay > 0 else RetryAction.RETRY_NOW,
        delay_seconds=delay,
        reason=rec.reason,
        suggested_params=dict(rec.proposed_params or {}),
    )


__all__ = [
    "RetryAction",
    "RetryDecision",
    "RetryPolicyConfig",
    "decide_retry",
]
