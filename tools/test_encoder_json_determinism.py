#!/usr/bin/env python3
"""Encoder.json regen determinism smoke (sub-phase 2c-c-6).

Verifies the contract documented in tools/generate_encoder_json.py:
  "re-running this tool on an unchanged Encoder.txt MUST produce a
   byte-identical Encoder.json. Any non-determinism is a bug."

Especially load-bearing post-2c-c-4 because slug derivation is new
code: NFKD normalization, hyphenation, and conditional collision
suffix all need to be deterministic across runs.

STRATEGY A (per STEP 2 of 2c-c-6 prompt): import the live tool's
TEXT_DEFAULTS module-level constant and replicate the same pipeline
(load_presets + append TEXT_DEFAULTS + save_presets_json) into a
tempdir, then md5-compare with the live assets/Encoder.json.

This avoids:
  - hardcoding Text-default Preset values (would drift from the tool)
  - subprocess invocation with --output (tool has no such flag)
  - backup-and-restore of live assets (risky if mid-run kill)

Run from repo root:

  python tools/test_encoder_json_determinism.py

Capture to tests/smoke-2c-c-6-regression-YYYYMMDD.log per ADR-0001.
Exits 0 on PASS.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.preset_loader import (  # noqa: E402
    derive_ids_for_presets,
    derive_slug,
    load_presets,
    save_presets_json,
)

ENCODER_TXT = REPO_ROOT / "assets" / "Encoder.txt"
ENCODER_JSON = REPO_ROOT / "assets" / "Encoder.json"


def md5_of_path(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_regen_byte_identical() -> bool:
    """STRATEGY A: import TEXT_DEFAULTS from tools.generate_encoder_json,
    re-run the same pipeline into tempdir, md5-compare with live file."""
    live_md5 = md5_of_path(ENCODER_JSON)
    print(f"  Live assets/Encoder.json md5: {live_md5}")

    gen_mod = importlib.import_module("tools.generate_encoder_json")
    text_defaults = gen_mod.TEXT_DEFAULTS
    fail_on_skip = gen_mod._fail_on_skip

    # Canonical counts: 106 in Encoder.txt + 2 hoisted Text defaults = 108 total.
    # Matches tools/generate_encoder_json.py and the live assets/Encoder.json.
    # Was 109/111 before the B-017 + 2c-c-* preset cleanup pass.
    file_presets = load_presets(ENCODER_TXT, on_error=fail_on_skip)
    if len(file_presets) != 106:
        print(f"  FAIL: expected 106 from Encoder.txt, got {len(file_presets)}")
        return False
    all_presets = file_presets + list(text_defaults)
    if len(all_presets) != 108:
        print(f"  FAIL: expected 108 total, got {len(all_presets)}")
        return False

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "Encoder.json"
        save_presets_json(tmp, all_presets)
        regen_md5 = md5_of_path(tmp)

    print(f"  Regen md5:                    {regen_md5}")

    if live_md5 != regen_md5:
        print("  FAIL: regen does not produce byte-identical Encoder.json")
        print("  This usually means one of:")
        print("    - assets/Encoder.txt changed but Encoder.json was not regenerated")
        print("    - slug derivation or json serialization is non-deterministic")
        print("    - generate_encoder_json.py source values drifted from live JSON")
        return False

    print("  PASS: regen byte-identical to live Encoder.json")
    return True


def test_slug_determinism() -> bool:
    """Run derive_slug + derive_ids_for_presets on the same inputs twice;
    assert identical output."""
    samples = [
        "Scale 99%",
        "Cycle 10s (4-3-3) 100x Zoom",
        "9:16 CRF High",
        "🕹️ 1vmo Ultimate",
        "80% Bottom",
    ]
    run1 = [derive_slug(s) for s in samples]
    run2 = [derive_slug(s) for s in samples]
    if run1 != run2:
        print(f"  FAIL: derive_slug not deterministic: {run1} vs {run2}")
        return False

    pairs = [("A", "Foo"), ("A", "Bar"), ("A", "Foo")]
    ids1 = derive_ids_for_presets(pairs, kind="builtin")
    ids2 = derive_ids_for_presets(pairs, kind="builtin")
    if ids1 != ids2:
        print(f"  FAIL: derive_ids_for_presets not deterministic: {ids1} vs {ids2}")
        return False

    print("  PASS: derive_slug + derive_ids_for_presets deterministic across runs")
    return True


def main() -> int:
    print("=== Encoder.json determinism smoke (sub-phase 2c-c-6) ===")
    print(f"Platform: {sys.platform}")
    print()
    tests = [
        ("Regen byte-identical to live", test_regen_byte_identical),
        ("Slug + id derivation deterministic", test_slug_determinism),
    ]
    results = []
    for name, fn in tests:
        print(f"[{name}]")
        results.append(fn())
        print()
    passed = sum(results)
    total = len(results)
    print(f"=== {passed}/{total} tests passed ===")
    if passed == total:
        print("PASS: determinism smoke green")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
