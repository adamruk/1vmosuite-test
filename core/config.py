"""Shared JSON config load/save for 1vmo Suite apps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppDefaults:
    """Single source of truth for runtime-tunable defaults.

    Mirrors the keys persisted by Settings dialog (`settings_dialog.py`)
    and consumed by `auto_render.py` (`VideoRendererTool.__init__`,
    `VideoRendererTool._reload_config_settings`, `RenderWorker.__init__`)
    and `core/preset_translator.py` (`translate_to_nvenc`).

    Values match the pre-Phase-A baseline:
      - GPU off by default; user opts in via Settings.
      - NVENC preset p4 per ADR-0007 D2 and ADR-0008's production guidance
        ("Production gpu_preset config default remains 'p4'.").
      - 2 concurrent NVENC sessions max (matches the previous hard-coded
        value; any future bump must be separately justified).
      - libx264-mapped NVENC codec choice is h264_nvenc per ADR-0007 D4.
      - retry_cpu on GPU encode failure; rename on output-path collision.

    Add fields here only when they need a centralized default; per-call
    overrides remain the responsibility of callers via `config.get(...)`
    or explicit kwarg.
    """

    gpu_enabled: bool = False
    gpu_preset: str = "p4"
    gpu_max_concurrent: int = 2
    gpu_codec: str = "h264_nvenc"
    gpu_error_action: str = "retry_cpu"
    output_collision: str = "rename"


APP_DEFAULTS = AppDefaults()


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
        with open(path, "r", encoding="utf-8") as f:
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

    v3.9 F-004 fix: route through core.atomic_write.save_json_atomic so
    a crash mid-write cannot corrupt config_video_renderer.json. Same
    on-disk contract used by Phase 3.1 queue_store + Phase 3.2
    score_store (tempfile write -> os.replace, with single-generation
    .bak rotation). The `indent` arg is honoured by atomic_write per
    its existing API; ensure_ascii=False is also preserved.
    """
    from core.atomic_write import save_json_atomic

    # save_json_atomic always uses ensure_ascii=False internally; we just
    # forward the indent kwarg.
    save_json_atomic(path, data, indent=indent)
