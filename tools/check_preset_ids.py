#!/usr/bin/env python3
"""Validate preset IDs in assets/Encoder.json (sub-phase 2c-c-4).

Per ADR-0006: every preset has a unique id matching ID_PATTERN.
Run from repo root:

  python tools/check_preset_ids.py

Capture to tests/smoke-2c-c-4-ids-YYYYMMDD.log per ADR-0001.
Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENCODER_JSON = REPO_ROOT / "assets" / "Encoder.json"

ID_PATTERN = re.compile(
    r"^(builtin:([a-z0-9-]+/)?[a-z0-9-]+(-\d+)?|user:[a-z0-9-]+(-\d+)?)$"
)


def main() -> int:
    print("=== Preset ID validation (sub-phase 2c-c-4) ===")
    print(f"File: {ENCODER_JSON}")

    data = json.loads(ENCODER_JSON.read_text(encoding="utf-8"))
    sv = data.get("schema_version")
    if sv != 2:
        print(f"FAIL: expected schema_version=2, got {sv}")
        return 1

    presets = data.get("presets", [])
    print(f"Total presets: {len(presets)}")

    ids = [p.get("id") for p in presets]
    bad_format = [i for i in ids if not (i and ID_PATTERN.match(i))]
    if bad_format:
        print(f"FAIL: {len(bad_format)} preset(s) have invalid id format")
        for i in bad_format[:5]:
            print(f"  - {i!r}")
        return 1
    print(f"PASS: all {len(ids)} ids match ID_PATTERN")

    if len(set(ids)) != len(ids):
        dupes = [i for i in set(ids) if ids.count(i) > 1]
        print(f"FAIL: {len(dupes)} duplicate id(s) found:")
        for i in dupes[:10]:
            print(f"  - {i} (x{ids.count(i)})")
        return 1
    print(f"PASS: all {len(ids)} ids are unique")

    non_builtin = [i for i in ids if not i.startswith("builtin:")]
    if non_builtin:
        print(f"FAIL: {len(non_builtin)} non-builtin id(s) in built-in library")
        for i in non_builtin[:5]:
            print(f"  - {i}")
        return 1
    print(f"PASS: all {len(ids)} ids are builtin:")

    layer_overlay = sorted([i for i in ids if "layer-overlay" in i])
    if len(layer_overlay) == 10:
        expected = sorted(
            f"builtin:1vmo-ultimate/layer-overlay-{n}" for n in range(1, 11)
        )
        if layer_overlay == expected:
            print("PASS: layer-overlay collision cluster suffixed -1..-10")
        else:
            print("FAIL: layer-overlay cluster mismatch")
            print(f"  expected: {expected}")
            print(f"  got:      {layer_overlay}")
            return 1

    print("\nPASS: preset IDs validate clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
