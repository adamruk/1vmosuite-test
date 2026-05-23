"""Smoke tests for `core.orchestration.retry_policy`. ADR-0003 narrow."""

from __future__ import annotations

from core.orchestration.retry_policy import (
    RetryAction,
    RetryPolicyConfig,
    decide_retry,
)


def test_default_disabled_returns_none():
    d = decide_retry("Cannot allocate memory", task_retry_count=0, batch_retry_count=0)
    assert d.action is RetryAction.NONE


def test_enabled_but_max_zero_returns_none():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=0)
    d = decide_retry(
        "Cannot allocate memory", task_retry_count=0, batch_retry_count=0, config=cfg
    )
    assert d.action is RetryAction.NONE


def test_eligible_kind_retries():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=2)
    d = decide_retry(
        "Cannot allocate memory",
        task_retry_count=0,
        batch_retry_count=0,
        config=cfg,
    )
    assert d.action in {RetryAction.RETRY_NOW, RetryAction.RETRY_LATER}
    assert d.suggested_params is not None


def test_ineligible_kind_returns_none():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=2)
    # "No such file" classifies to DEBUG_LOG which is NOT retry-eligible.
    d = decide_retry(
        "No such file or directory: /tmp/a.mp4",
        task_retry_count=0,
        batch_retry_count=0,
        config=cfg,
    )
    assert d.action is RetryAction.NONE


def test_task_ceiling_blocks_retry():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=1)
    d = decide_retry("I/O error", task_retry_count=1, batch_retry_count=0, config=cfg)
    assert d.action is RetryAction.NONE


def test_batch_ceiling_blocks_retry():
    cfg = RetryPolicyConfig(
        enabled=True, max_retries_per_task=3, max_retries_per_batch=2
    )
    d = decide_retry("I/O error", task_retry_count=0, batch_retry_count=2, config=cfg)
    assert d.action is RetryAction.NONE


def test_unknown_pattern_returns_none():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=2)
    d = decide_retry(
        "Some completely novel error xyz",
        task_retry_count=0,
        batch_retry_count=0,
        config=cfg,
    )
    assert d.action is RetryAction.NONE


def test_backoff_grows_with_retry_count():
    cfg = RetryPolicyConfig(enabled=True, max_retries_per_task=3)
    d0 = decide_retry("I/O error", task_retry_count=0, batch_retry_count=0, config=cfg)
    d1 = decide_retry("I/O error", task_retry_count=1, batch_retry_count=0, config=cfg)
    d2 = decide_retry("I/O error", task_retry_count=2, batch_retry_count=0, config=cfg)
    assert d0.delay_seconds <= d1.delay_seconds <= d2.delay_seconds
