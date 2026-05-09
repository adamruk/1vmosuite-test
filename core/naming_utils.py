"""Filename construction utilities for 1vmo Suite output paths.

Ported from Phase 1 naming_utils.py (1vmo-suite/naming_utils.py, 57 lines)
with the avoid_collision TOCTOU race (PORT_NOTES Bug 9) fixed at port time:
the inner os.path.exists() check is replaced with an atomic
open(candidate, 'x').close() exclusive create per CPython 3.3+ 'x' mode.

The 'x' mode maps to O_CREAT | O_EXCL on POSIX (atomic create-or-fail) and
the equivalent CreateFileW with CREATE_NEW disposition on Windows. Two
concurrent workers calling avoid_collision() with the same target path
will get distinct candidates because only one can win the exclusive create.

Trade-off documented in PORT_NOTES line 285: a 0-byte placeholder file is
left at the returned path. The caller (ffmpeg invocation) overwrites it
immediately. If ffmpeg crashes before writing, the 0-byte file remains as
a marker — this is intentional and preferred over silent overwrite of an
in-flight encode by a parallel worker.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

MAX_FILENAME = 59  # hard ceiling, including extension

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def timestamp() -> str:
    """Sortable timestamp: YYYYMMDD_HHMMSS (15 chars, 4-digit year per ISO 8601)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_part(name: str, max_len: int) -> str:
    """Strip illegal chars, collapse whitespace/underscores, clip to max_len."""
    if not name:
        return "x"
    name = os.path.splitext(os.path.basename(name))[0]
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_ ")
    if not name:
        return "x"
    return name[:max_len] if max_len > 0 else "x"


def clip_to_limit(filename: str, max_total: int = MAX_FILENAME) -> str:
    """Last-resort guard. Truncates the base, preserves the extension."""
    if len(filename) <= max_total:
        return filename
    base, ext = os.path.splitext(filename)
    keep = max_total - len(ext)
    if keep < 1:
        return filename[:max_total]
    return base[:keep] + ext


def avoid_collision(path: str) -> str:
    """If path is unclaimed, atomically reserve it. Else append _1, _2, ... until success.

    TOCTOU-safe per PORT_NOTES Bug 9 fix: uses atomic exclusive create
    (open(candidate, 'x').close()) instead of the unsafe Phase-1 pattern of
    os.path.exists() check followed by return-without-create. Two concurrent
    workers calling this with the same target will get distinct candidates
    because only one can win the FileExistsError race per call.

    Leaves a 0-byte placeholder at the returned path. Caller overwrites
    immediately via ffmpeg. See module docstring for trade-off rationale.
    """
    folder = os.path.dirname(path)
    name = os.path.basename(path)
    base, ext = os.path.splitext(name)

    # Try the original path first via atomic exclusive create.
    try:
        open(path, "x").close()
        return path
    except FileExistsError:
        pass

    # Original is taken — try numbered suffixes until one wins.
    n = 1
    while True:
        suffix = f"_{n}"
        keep = MAX_FILENAME - len(ext) - len(suffix)
        if keep < 1:
            keep = 1
        candidate = os.path.join(folder, f"{base[:keep]}{suffix}{ext}")
        try:
            open(candidate, "x").close()
            return candidate
        except FileExistsError:
            n += 1
            if n > 9999:
                # Last-resort: return the candidate even though we couldn't reserve it.
                # Caller will get a real error when ffmpeg fails to open it.
                return candidate
