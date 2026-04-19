#!/usr/bin/env python3
"""Phase 2c-a: Encoder.txt → Encoder.json migration tool.

Reads assets/Encoder.txt via core.preset_loader, appends the 2 Text defaults
currently hardcoded in auto_render.py (lines 512-525), writes assets/Encoder.json.

Schema v1 contract:
  - Root object: {"schema_version": 1, "presets": [...]}
  - Each preset entry: {
        "group":       str,   # may be empty string, UTF-8 with emoji/Vietnamese
        "name":        str,   # non-empty, UTF-8
        "description": str,   # may be empty string
        "details":     str,   # may be empty string
        "params":      list[str],  # JSON has no tuple; loader reconstructs as tuple
    }
  - Field order within each preset: group, name, description, details, params
    (matches Preset dataclass field order; relied on for deterministic output)
  - Preset ordering: Encoder.txt file order, then Text defaults (Bottom, Top)
  - Encoding: UTF-8, ensure_ascii=False (emoji/Vietnamese not escaped)
  - Line endings: LF only (newline='\\n'), regardless of platform
  - Indentation: 2 spaces

v1 does NOT include a 'source' field (builtin vs user). If a future preset-
editor UI needs that distinction, migrate to v2 via a separate tool.

Determinism: re-running this tool on an unchanged Encoder.txt MUST produce a
byte-identical Encoder.json. Any non-determinism is a bug.

Parse skips are FATAL: load_presets() defaults to print()ing on skip, which
would silently drop presets. This tool passes a callback that raises SystemExit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make core/ importable when running this tool from repo root or tools/
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import preset_loader  # noqa: E402
from dataclasses import asdict  # noqa: E402


ENCODER_TXT = _REPO_ROOT / 'assets' / 'Encoder.txt'
ENCODER_JSON = _REPO_ROOT / 'assets' / 'Encoder.json'
SCHEMA_VERSION = 1


# Text defaults — verbatim from auto_render.py lines 512-525. DO NOT EDIT.
TEXT_DEFAULTS = [
    preset_loader.Preset(
        group='Text',
        name='Text Bottom Basic',
        description='Thêm chữ ở dưới với nền đen mờ',
        details='Thêm chữ ở dưới video với nền đen mờ, font Arial, size 35px',
        params=('-vf', "drawtext=fontfile=Arial:text='THAY_THẾ_NỘI_DUNG':x=(w-text_w)/2:y=(h-text_h)/1.05:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10"),
    ),
    preset_loader.Preset(
        group='Text',
        name='Text Top Basic',
        description='Thêm chữ ở trên với nền đen mờ',
        details='Thêm chữ ở trên video với nền đen mờ, font Arial, size 35px',
        params=('-vf', "drawtext=fontfile=Arial:text='THAY_THẾ_NỘI_DUNG':x=(w-text_w)/2:y=(h-text_h)/15:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10"),
    ),
]


def _fail_on_skip(line_num: int, line: str, reason: str) -> None:
    """Parse-skip callback: treat any skip as fatal. Migration is lossless or not at all."""
    raise SystemExit(
        f"FATAL: Encoder.txt line {line_num} failed to parse: {reason}\n"
        f"  Line content: {line!r}\n"
        f"  Aborting migration. Fix Encoder.txt or investigate core.preset_loader before retrying."
    )


def main() -> int:
    if not ENCODER_TXT.exists():
        raise SystemExit(f"FATAL: {ENCODER_TXT} not found. Wrong cwd?")

    # 1. Parse Encoder.txt via the existing loader with fail-loud callback
    file_presets = preset_loader.load_presets(ENCODER_TXT, on_error=_fail_on_skip)
    if len(file_presets) != 109:
        raise SystemExit(
            f"FATAL: expected 109 presets from Encoder.txt, got {len(file_presets)}. "
            "Either Encoder.txt drifted or the parser changed. Investigate before migrating."
        )

    # 2. Append Text defaults (order: Bottom, Top — matches auto_render.py lines 512→519)
    all_presets = file_presets + TEXT_DEFAULTS
    if len(all_presets) != 111:
        raise SystemExit(f"FATAL: expected 111 total presets, got {len(all_presets)}")

    # 3. Serialize. asdict() converts tuple(params) → list(params) naturally.
    payload = {
        'schema_version': SCHEMA_VERSION,
        'presets': [asdict(p) for p in all_presets],
    }

    # 4. Write deterministically: LF-only, UTF-8 verbatim, 2-space indent, no key sort
    ENCODER_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ENCODER_JSON, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write('\n')  # trailing newline — POSIX convention, consistent across re-runs

    print(f"Wrote {ENCODER_JSON} with {len(all_presets)} presets (schema v{SCHEMA_VERSION})")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
