"""Shared JSON config load/save for 1vmo Suite apps."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load a JSON config file.

    Args:
        path: Path to the JSON file.
        default: Returned when file is missing or corrupt. If None, returns {}.

    Returns:
        Parsed dict on success, a copy of default on missing/corrupt file.
        Never raises; file errors and JSON errors both fall through to default.
    """
    if default is None:
        default = {}
    if not path.exists():
        return dict(default)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(default)


def save(path: Path, data: dict[str, Any], indent: int = 4) -> None:
    """Save a dict as JSON with UTF-8 encoding.

    Args:
        path: Path to write to.
        data: Dict to serialize.
        indent: JSON indent (default 4 matches existing behavior).

    Raises:
        OSError: If the file cannot be written.
        TypeError: If data contains non-JSON-serializable values.

    Callers should wrap in try/except and show UI error if appropriate.
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
