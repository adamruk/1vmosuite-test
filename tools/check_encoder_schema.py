#!/usr/bin/env python3
"""Manual-smoke validator for assets/Encoder.json against the Pydantic schema.

Aligned with ADR-0001 (smoke-logs-only convention; no pytest).
Run from repo root: python tools/check_encoder_schema.py
Capture output to tests/smoke-2c-c-1-schema-YYYYMMDD.log.
Exits 0 on PASS, non-zero on FAIL with reason.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.encoder_schema import EncoderLibrary  # noqa: E402


# Canonical count: 108 = 106 from Encoder.txt + 2 hoisted Text defaults
# (matches tools/generate_encoder_json.py lines 92/100). Was 111 before
# the post-B-017 preset audit and the 2c-c-* cleanup pass. Historical
# smoke logs in tests/smoke-2c-c-*-20260426/27.log are immutable and
# still show the older 111 figure — that is intentional and expected.
EXPECTED_PRESET_COUNT = 108


def main() -> int:
    encoder_json = REPO_ROOT / "assets" / "Encoder.json"
    if not encoder_json.exists():
        print(f"FAIL: {encoder_json} not found")
        return 1

    try:
        raw = json.loads(encoder_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: JSON decode error: {e}")
        return 2

    try:
        library = EncoderLibrary.model_validate(raw)
    except Exception as e:
        print(f"FAIL: Pydantic validation error: {type(e).__name__}: {e}")
        return 3

    actual = len(library.presets)
    if actual != EXPECTED_PRESET_COUNT:
        print(
            f"FAIL: preset count mismatch: expected {EXPECTED_PRESET_COUNT}, got {actual}"
        )
        return 4

    print(f"PASS: {encoder_json.name} validates against EncoderLibrary schema")
    print(f"  schema_version: {library.schema_version}")
    print(f"  preset count: {actual}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
