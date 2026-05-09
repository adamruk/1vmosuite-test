"""ADR-0003 Exception 1: atomic write retry under contention.

Run via:  pytest tests/smoke/test_atomic_write_retry.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.atomic_write import RETRY_BACKOFFS_MS, save_json_atomic


def test_retry_succeeds_after_transient_permission_errors(tmp_path: Path) -> None:
    """os.replace fails 4 times then succeeds; should still write."""
    target = tmp_path / "data.json"
    data = {"a": 1, "b": [1, 2, 3]}

    original_replace = os.replace
    call_count = {"n": 0}

    def flaky_replace(src, dst):
        call_count["n"] += 1
        if call_count["n"] <= 4:
            raise PermissionError("simulated AV/OneDrive lock")
        return original_replace(src, dst)

    with patch("core.atomic_write.os.replace", side_effect=flaky_replace):
        save_json_atomic(target, data)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == data
    assert call_count["n"] == 5


def test_retry_exhaustion_raises(tmp_path: Path) -> None:
    """os.replace fails always; should raise after exhausting retries."""
    target = tmp_path / "data.json"

    with patch(
        "core.atomic_write.os.replace",
        side_effect=PermissionError("permanent lock"),
    ):
        with pytest.raises(PermissionError):
            save_json_atomic(target, {"k": "v"})


def test_backoff_count_matches_constant() -> None:
    """Document expected retry count via the constant."""
    assert len(RETRY_BACKOFFS_MS) == 5
    assert sum(RETRY_BACKOFFS_MS) == 1550
