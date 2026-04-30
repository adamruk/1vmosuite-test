"""Atomic JSON write with .bak rotation + retry (sub-phase 2c-c-3).

Generic primitive used by user-state writers. Behavior:
  1. Serialize data to JSON bytes FIRST so encoding errors raise pre-disk.
  2. Write to <path>.tmp; flush; fsync.
  3. If <path> exists: rotate <path> -> <path>.bak (single generation).
  4. os.replace(<path>.tmp, <path>) wrapped in 5-attempt loop with
     exponential backoff between attempts (50/100/200/400ms sleeps = 750ms
     total max wait).
  5. On any failure: clean up .tmp; raise.

No directory fsync (matches core/preset_loader.py:228 design note).
Single-generation .bak (per ADR-0002: "multi-generation rotation
is sufficient for team use" -- single-gen).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# 5 attempts with sleeps between them (4 actual sleeps).
# Final 800ms entry preserved for symmetry; loop raises before
# using it. Total max wait: 750ms (50+100+200+400).
RETRY_BACKOFFS_MS = (50, 100, 200, 400, 800)


def save_json_atomic(
    path: Path,
    data: Any,
    indent: int = 2,
) -> None:
    """Atomically write data as JSON to path with .bak rotation + retry.

    Args:
        path: Destination JSON file. Parent dir must exist (caller's job).
        data: JSON-serializable object.
        indent: json.dump indent kwarg (default 2).

    Raises:
        TypeError / ValueError: serialization failure (no disk touched).
        PermissionError / OSError: terminal failure after all retries.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=False)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    bak_path = path.with_suffix(path.suffix + ".bak")

    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        if path.exists():
            os.replace(path, bak_path)

        last_exc: Exception | None = None
        for attempt, backoff_ms in enumerate(RETRY_BACKOFFS_MS):
            try:
                os.replace(tmp_path, path)
                return
            except (PermissionError, OSError) as e:
                last_exc = e
                if attempt < len(RETRY_BACKOFFS_MS) - 1:
                    time.sleep(backoff_ms / 1000.0)

        if last_exc is not None:
            raise last_exc

    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
