"""Phase 3.2 — local persistent score cache.

Mirrors `core/queue_store.py` design (atomic write + schema-version
reject + never-raises load), with one structural difference: this is
a multi-row cache (one row per scored pair), not a single-batch
snapshot.

On-disk shape:
    {
      "schema_version": 1,
      "rows": {
        "<cache_key>": { ...ScoreResult fields... },
        ...
      }
    }

Cache key = sha256(reference_path + "\\x00" + distorted_path). We
store the mtime of both files inside the row; on lookup the caller
can compare the cached mtimes against the current ones and treat a
mismatch as a cache miss (in-place re-render invalidates the score).

File lock: NOT used here. The score cache is single-writer in
practice (the ScoreWorker pool serialises writes through a
QMutex), and even in the multi-instance edge case the worst-case
outcome is "one of two recent scores wins" — no corruption,
because every write is atomic via save_json_atomic.

Local-only — same invariant as the Phase 3.1 queue store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from pydantic import ValidationError

from core.atomic_write import save_json_atomic
from core.scoring.score_models import SCORE_SCHEMA_VERSION, ScoreResult

logger = logging.getLogger("core.scoring.score_store")

SCORE_CACHE_FILENAME = "scores.json"


def _cache_key(reference_path: str, distorted_path: str) -> str:
    """Stable cache key — sha256 hash of the two paths."""
    h = hashlib.sha256()
    h.update(reference_path.encode("utf-8"))
    h.update(b"\x00")
    h.update(distorted_path.encode("utf-8"))
    return h.hexdigest()


class ScoreCache:
    """In-memory cache of ScoreResult rows, persisted to disk.

    Public API:
        ScoreCache(user_data_dir)             - constructor
        get(reference, distorted) -> Optional - lookup, with mtime check
        put(score_result)                     - insert/update + persist
        clear()                               - drop all rows + remove file
        rows() -> Iterable[ScoreResult]       - iterate (for diagnostics)

    Thread-safety:
        Internal threading.Lock guards the dict and the write. Caller
        may invoke from any thread (ScoreWorker uses this).
    """

    def __init__(self, user_data_dir: Path):
        self._user_data_dir = Path(user_data_dir)
        self._cache_path = self._user_data_dir / SCORE_CACHE_FILENAME
        self._mem_lock = threading.Lock()
        self._rows: Dict[str, ScoreResult] = {}
        self._load_from_disk()

    # --------------------------------------------------------------
    # Internal
    # --------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Best-effort load. Never raises — corrupt cache is just empty."""
        if not self._cache_path.is_file():
            return
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as exc:
            logger.warning("score_store: cannot read cache: %s", exc)
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("score_store: cache file is corrupt: %s", exc)
            return
        if not isinstance(data, dict):
            logger.warning("score_store: cache payload is not an object")
            return
        sv = data.get("schema_version")
        if sv != SCORE_SCHEMA_VERSION:
            logger.warning(
                "score_store: schema version mismatch (file=%r, expected=%d); "
                "starting with an empty cache",
                sv,
                SCORE_SCHEMA_VERSION,
            )
            return
        rows = data.get("rows")
        if not isinstance(rows, dict):
            return
        loaded: Dict[str, ScoreResult] = {}
        for key, row in rows.items():
            if not isinstance(row, dict):
                continue
            try:
                loaded[key] = ScoreResult.model_validate(row)
            except ValidationError as exc:
                logger.debug("score_store: dropping invalid row %s: %s", key, exc)
                continue
        with self._mem_lock:
            self._rows = loaded
        logger.debug("score_store: loaded %d row(s) from disk", len(loaded))

    def _persist_locked(self) -> None:
        """Write self._rows to disk. Caller must hold _mem_lock."""
        payload = {
            "schema_version": SCORE_SCHEMA_VERSION,
            "rows": {k: v.model_dump(mode="json") for k, v in self._rows.items()},
        }
        try:
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
            save_json_atomic(self._cache_path, payload)
        except OSError as exc:
            logger.warning("score_store: persist failed: %s", exc)

    # --------------------------------------------------------------
    # Public
    # --------------------------------------------------------------

    def get(
        self,
        reference_path: str,
        distorted_path: str,
        *,
        reference_mtime: Optional[float] = None,
        distorted_mtime: Optional[float] = None,
    ) -> Optional[ScoreResult]:
        """Return the cached row for (reference, distorted), or None.

        Optional mtime parameters: when provided, a stale cache hit
        (mtimes don't match) returns None so the caller re-scores.
        Without them, any cached row matches.
        """
        key = _cache_key(reference_path, distorted_path)
        with self._mem_lock:
            row = self._rows.get(key)
        if row is None:
            return None
        if reference_mtime is not None and row.reference_mtime != reference_mtime:
            return None
        if distorted_mtime is not None and row.distorted_mtime != distorted_mtime:
            return None
        return row

    def put(self, score: ScoreResult) -> None:
        """Insert/update a row and persist. Caller chooses when to call."""
        key = _cache_key(score.reference_path, score.distorted_path)
        with self._mem_lock:
            self._rows[key] = score
            self._persist_locked()

    def clear(self) -> None:
        """Drop all rows and remove the file. Idempotent."""
        with self._mem_lock:
            self._rows.clear()
            try:
                self._cache_path.unlink(missing_ok=True)
                # Atomic-write rotation may have left a sibling .bak;
                # clean it too so a `clear()` really wipes state.
                bak = self._cache_path.with_suffix(self._cache_path.suffix + ".bak")
                bak.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("score_store: clear failed: %s", exc)

    def rows(self) -> Iterable[Tuple[str, ScoreResult]]:
        """Iterate (key, row). Snapshot — safe under concurrent puts."""
        with self._mem_lock:
            snapshot = list(self._rows.items())
        return iter(snapshot)

    def __len__(self) -> int:
        with self._mem_lock:
            return len(self._rows)


__all__ = [
    "ScoreCache",
    "SCORE_CACHE_FILENAME",
]
