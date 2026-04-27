# VMAF Validation: v2.5 GPU Pipeline

**Status:** **FAIL** - per-codec offset adjustment required
**Latest run:** 2026-04-28 04:30 (revised 4-clip set per Step 4e-fix-1)
**ADR:** ADR-0007 D9
**Hardware:** RTX 4080 Laptop GPU (Ada Lovelace), driver 591.44
**FFmpeg:** ffmpeg version N-120402-g7c5319e692-20250729 Copyright (c) 2000-2025 the FFmpeg developers

## Revision History

- **2026-04-28 Step 4e (commit 4cff4f0):** Original 3-clip run. Verdict FAIL (5 of 9 missed p5 >= 97.0).
- **2026-04-28 Step 4e-fix-1 (this revision):** Hybrid remediation per Adam. Replaced clip3_x3speed (artificial worst case) with clip3_typical (D:/render/9.mp4). Added clip4_diverse (D:/render/6.mp4). Pass criterion UNCHANGED (ADR-0007 D9 immutable).

## Pass Criterion (ADR-0007 D9, UNCHANGED)

- VMAF mean must be >= 98.0
- VMAF p5 (5th percentile) must be >= 97.0
- Both criteria must hold across all 3 codecs for ALL clips

## Test Parameters

- CPU CRF: 20 | NVENC CQ: 22 (CRF + 2 per ADR-0007 D3)
- NVENC preset: p4 | rate control: vbr | b:v 0 | multipass 0
- VMAF model: vmaf_v0.6.1

## Reference Clips (Revised Set)

| Label | Path | Content Type |
|-------|------|--------------|
| clip1_motion | D:/render/1.mp4 | escalator/motion (KEPT) |
| clip2_face | D:/render/13.mp4 | face/close-up (KEPT) |
| clip3_typical | D:/render/9.mp4 | typical fast-action (REPLACED clip3_x3speed) |
| clip4_diverse | D:/render/6.mp4 | content diversity (NEW) |

## Results Table (Latest 4-clip Run)

| Clip | Codec | VMAF Mean | VMAF p5 | Verdict |
|------|-------|-----------|---------|---------|
| clip1_motion | h264 | 98.42 | 97.12 | PASS |
| clip1_motion | hevc | 98.65 | 97.29 | PASS |
| clip1_motion | av1 | 99.20 | 98.06 | PASS |
| clip2_face | h264 | 98.78 | 96.03 | FAIL |
| clip2_face | hevc | 98.92 | 96.31 | FAIL |
| clip2_face | av1 | 99.35 | 97.01 | PASS |
| clip3_typical | h264 | 97.21 | 93.97 | FAIL |
| clip3_typical | hevc | 97.15 | 94.10 | FAIL |
| clip3_typical | av1 | 98.13 | 95.47 | FAIL |
| clip4_diverse | h264 | 97.26 | 93.60 | FAIL |
| clip4_diverse | hevc | 97.24 | 93.57 | FAIL |
| clip4_diverse | av1 | 98.11 | 95.18 | FAIL |

## Per-Codec Summary

| Codec | Mean (avg of 4) | p5 (worst of 4) | All Pass? |
|-------|----------------|-----------------|-----------|
| h264 | 97.92 | 93.60 | NO |
| hevc | 97.99 | 93.57 | NO |
| av1 | 98.70 | 95.18 | NO |

## Encode Performance (Latest Run)

| Clip | Codec | CPU Time | GPU Time | Speedup | CPU MB | GPU MB |
|------|-------|---------|---------|---------|--------|--------|
| clip1_motion | h264 | 1.8s | 0.71s | 2.5x | 4.6 | 5.9 |
| clip1_motion | hevc | 6.64s | 0.82s | 8.1x | 5.1 | 5.8 |
| clip1_motion | av1 | 6.43s | 0.74s | 8.7x | 7.0 | 7.5 |
| clip2_face | h264 | 2.03s | 0.71s | 2.9x | 4.8 | 6.6 |
| clip2_face | hevc | 7.37s | 0.78s | 9.4x | 5.1 | 6.3 |
| clip2_face | av1 | 7.2s | 0.71s | 10.1x | 6.6 | 7.5 |
| clip3_typical | h264 | 1.84s | 0.73s | 2.5x | 4.9 | 6.8 |
| clip3_typical | hevc | 7.36s | 0.79s | 9.3x | 6.0 | 6.7 |
| clip3_typical | av1 | 8.52s | 0.95s | 9.0x | 8.0 | 8.9 |
| clip4_diverse | h264 | 1.72s | 0.78s | 2.2x | 5.0 | 7.0 |
| clip4_diverse | hevc | 8.16s | 0.76s | 10.7x | 6.3 | 6.9 |
| clip4_diverse | av1 | 8.83s | 0.84s | 10.5x | 8.6 | 9.1 |

## Verdict

**FAIL.** One or more pairings missed criteria with revised clip set. Per-codec offset adjustment required (Path A). Specific failures:

- clip2_face / h264: mean=98.784326, p5=96.02611, mean_pass=True, p5_pass=False
- clip2_face / hevc: mean=98.923298, p5=96.311361, mean_pass=True, p5_pass=False
- clip3_typical / h264: mean=97.214582, p5=93.965849, mean_pass=False, p5_pass=False
- clip3_typical / hevc: mean=97.148232, p5=94.096526, mean_pass=False, p5_pass=False
- clip3_typical / av1: mean=98.13412, p5=95.472415, mean_pass=True, p5_pass=False
- clip4_diverse / h264: mean=97.26131, p5=93.597124, mean_pass=False, p5_pass=False
- clip4_diverse / hevc: mean=97.236114, p5=93.574754, mean_pass=False, p5_pass=False
- clip4_diverse / av1: mean=98.113965, p5=95.178379, mean_pass=True, p5_pass=False

## Original 3-clip run (2026-04-28, commit 4cff4f0)

Preserved verbatim per ADR best practice. Original verdict: FAIL

| Clip | Codec | VMAF Mean | VMAF p5 | Verdict |
|------|-------|-----------|---------|---------|
| clip1_motion | h264 | 98.42 | 97.12 | PASS |
| clip1_motion | hevc | 98.65 | 97.29 | PASS |
| clip1_motion | av1 | 99.20 | 98.06 | PASS |
| clip2_face | h264 | 98.78 | 96.03 | FAIL |
| clip2_face | hevc | 98.92 | 96.31 | FAIL |
| clip2_face | av1 | 99.35 | 97.01 | PASS |
| clip3_x3speed | h264 | 98.01 | 93.66 | FAIL |
| clip3_x3speed | hevc | 98.00 | 93.66 | FAIL |
| clip3_x3speed | av1 | 99.16 | 95.84 | FAIL |

## Reproducibility

Working files at benchmarks/_vmaf_work/. .mp4 files gitignored (regenerable). Per-frame VMAF JSON logs are tracked.
