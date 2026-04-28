# VMAF Validation: v2.5 GPU Pipeline

**Status:** **FAIL** - further calibration needed (Step 4e-fix-4)
**Latest run:** 2026-04-28 05:47 (Step 4e-fix-3 - Max Quality Mode preset=p7 multipass=2)
**ADR:** ADR-0007 D9
**Hardware:** RTX 4080 Laptop GPU (Ada Lovelace), driver 591.44
**FFmpeg:** ffmpeg version N-120402-g7c5319e692-20250729 Copyright (c) 2000-2025 the FFmpeg developers

## Revision History

- **2026-04-28 Step 4e (commit 4cff4f0):** Original 3-clip run. Verdict FAIL.
- **2026-04-28 Step 4e-fix-1 (commit c1f5ea8):** Hybrid remediation (replace clip3 + add clip4). Verdict FAIL.
- **2026-04-28 Step 4e-fix-2 (commit bf3fa39):** Path A - per-codec offset calibration. Verdict FAIL (improvement real but insufficient).
- **2026-04-28 Step 4e-fix-3 (this run):** Max Quality Mode per ADR-0007 D7 - preset=p7 + multipass=2. Verdict: FAIL


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



## Step 4e-fix-3 results (Max Quality Mode per ADR-0007 D7)

NVENC preset p7 + multipass=2; per-codec offsets unchanged from fix-2.

| Codec | fix-2 mean | fix-3 mean | delta mean | fix-2 p5 | fix-3 p5 | delta p5 |
|-------|------------|------------|------------|----------|----------|----------|
| h264_nvenc | 98.21 | 98.25 | +0.04 | 94.19 | 94.23 | +0.04 |
| hevc_nvenc | 98.26 | 98.29 | +0.03 | 94.17 | 94.21 | +0.04 |
| av1_nvenc | 98.88 | 98.89 | +0.01 | 95.67 | 95.70 | +0.03 |

### Results Table (Step 4e-fix-3)

| Clip | Codec | CQ | Preset | MP | VMAF Mean | VMAF p5 | Verdict |
|------|-------|-----|--------|----|-----------|---------|---------|
| clip1_motion | h264 | 20 | p7 | 2 | 98.73 | 97.33 | PASS |
| clip1_motion | hevc | 20 | p7 | 2 | 98.91 | 97.63 | PASS |
| clip1_motion | av1 | 19 | p7 | 2 | 99.46 | 98.40 | PASS |
| clip2_face | h264 | 20 | p7 | 2 | 99.02 | 96.53 | FAIL |
| clip2_face | hevc | 20 | p7 | 2 | 99.13 | 96.68 | FAIL |
| clip2_face | av1 | 19 | p7 | 2 | 99.46 | 97.22 | PASS |
| clip3_typical | h264 | 20 | p7 | 2 | 97.58 | 94.40 | FAIL |
| clip3_typical | hevc | 20 | p7 | 2 | 97.49 | 94.60 | FAIL |
| clip3_typical | av1 | 19 | p7 | 2 | 98.32 | 95.85 | FAIL |
| clip4_diverse | h264 | 20 | p7 | 2 | 97.66 | 94.23 | FAIL |
| clip4_diverse | hevc | 20 | p7 | 2 | 97.61 | 94.21 | FAIL |
| clip4_diverse | av1 | 19 | p7 | 2 | 98.31 | 95.70 | FAIL |

### Encode Performance (Max Quality Mode tradeoff)

| Clip | Codec | CPU Time | GPU Time | Speedup | CPU MB | GPU MB | GPU/CPU |
|------|-------|----------|----------|---------|--------|--------|---------|
| clip1_motion | h264 | 1.81s | 1.11s | 1.6x | 4.6 | 7.5 | 1.63x |
| clip1_motion | hevc | 7.08s | 1.24s | 5.7x | 5.1 | 7.2 | 1.40x |
| clip1_motion | av1 | 6.85s | 1.15s | 6.0x | 7.0 | 9.8 | 1.40x |
| clip2_face | h264 | 1.94s | 1.26s | 1.5x | 4.8 | 8.1 | 1.67x |
| clip2_face | hevc | 7.51s | 1.34s | 5.6x | 5.1 | 7.7 | 1.50x |
| clip2_face | av1 | 7.93s | 1.17s | 6.8x | 6.6 | 9.6 | 1.46x |
| clip3_typical | h264 | 2.14s | 1.41s | 1.5x | 4.9 | 8.8 | 1.81x |
| clip3_typical | hevc | 8.94s | 1.38s | 6.5x | 6.0 | 8.3 | 1.40x |
| clip3_typical | av1 | 11.06s | 1.36s | 8.1x | 8.0 | 11.5 | 1.43x |
| clip4_diverse | h264 | 1.92s | 1.29s | 1.5x | 5.0 | 9.0 | 1.81x |
| clip4_diverse | hevc | 8.91s | 1.38s | 6.5x | 6.3 | 8.7 | 1.37x |
| clip4_diverse | av1 | 8.15s | 1.28s | 6.4x | 8.6 | 11.9 | 1.38x |

### Verdict

**FAIL.** Max Quality Mode reduced p5 misses but did not clear all D9 thresholds. Step 4e-fix-4 needed (tune=hq experiment OR tolerance amendment via ADR-0008). Failures:

- clip2_face / h264 (CQ=20): mean=99.024188, p5=96.525605
- clip2_face / hevc (CQ=20): mean=99.132545, p5=96.679899
- clip3_typical / h264 (CQ=20): mean=97.580375, p5=94.400864
- clip3_typical / hevc (CQ=20): mean=97.493628, p5=94.597759
- clip3_typical / av1 (CQ=19): mean=98.324598, p5=95.848745
- clip4_diverse / h264 (CQ=20): mean=97.656827, p5=94.228361
- clip4_diverse / hevc (CQ=20): mean=97.605502, p5=94.207198
- clip4_diverse / av1 (CQ=19): mean=98.313643, p5=95.699353

## Step 4e-fix-2 results (per-codec offset calibration)

Per-codec CRF->CQ offsets calibrated empirically:

| Codec | Old offset | New offset | Old mean | New mean | Old p5 | New p5 |
|-------|------------|------------|----------|----------|--------|--------|
| h264_nvenc | +2 | +0 | 97.92 | 98.21 | 93.60 | 94.19 |
| hevc_nvenc | +2 | +0 | 97.99 | 98.26 | 93.57 | 94.17 |
| av1_nvenc | +2 | -1 | 98.70 | 98.88 | 95.18 | 95.67 |

### Results Table (Step 4e-fix-2)

| Clip | Codec | CQ | VMAF Mean | VMAF p5 | Verdict |
|------|-------|-----|-----------|---------|---------|
| clip1_motion | h264 | 20 | 98.70 | 97.34 | PASS |
| clip1_motion | hevc | 20 | 98.90 | 97.60 | PASS |
| clip1_motion | av1 | 19 | 99.45 | 98.40 | PASS |
| clip2_face | h264 | 20 | 98.99 | 96.44 | FAIL |
| clip2_face | hevc | 20 | 99.10 | 96.66 | FAIL |
| clip2_face | av1 | 19 | 99.45 | 97.24 | PASS |
| clip3_typical | h264 | 20 | 97.52 | 94.39 | FAIL |
| clip3_typical | hevc | 20 | 97.47 | 94.55 | FAIL |
| clip3_typical | av1 | 19 | 98.31 | 95.82 | FAIL |
| clip4_diverse | h264 | 20 | 97.61 | 94.19 | FAIL |
| clip4_diverse | hevc | 20 | 97.57 | 94.17 | FAIL |
| clip4_diverse | av1 | 19 | 98.31 | 95.67 | FAIL |

### File-size deltas (Step 4e-fix-2)

Lower CQ = larger files. Tradeoff visibility for tag-readiness assessment.

| Clip | Codec | CPU MB | GPU MB | GPU/CPU ratio |
|------|-------|--------|--------|---------------|
| clip1_motion | h264 | 4.6 | 7.4 | 1.60x |
| clip1_motion | hevc | 5.1 | 7.3 | 1.42x |
| clip1_motion | av1 | 7.0 | 9.8 | 1.40x |
| clip2_face | h264 | 4.8 | 8.1 | 1.68x |
| clip2_face | hevc | 5.1 | 7.8 | 1.52x |
| clip2_face | av1 | 6.6 | 9.7 | 1.48x |
| clip3_typical | h264 | 4.9 | 8.6 | 1.76x |
| clip3_typical | hevc | 6.0 | 8.4 | 1.41x |
| clip3_typical | av1 | 8.0 | 11.5 | 1.43x |
| clip4_diverse | h264 | 5.0 | 8.9 | 1.79x |
| clip4_diverse | hevc | 6.3 | 8.7 | 1.38x |
| clip4_diverse | av1 | 8.6 | 12.0 | 1.39x |

### Verdict

**FAIL.** Per-codec offsets reduced means/p5 but not enough to clear all thresholds. Step 4e-fix-3 needed (further offset reduction). Failures:

- clip2_face / h264 (CQ=20): mean=98.993938, p5=96.435381
- clip2_face / hevc (CQ=20): mean=99.099567, p5=96.664258
- clip3_typical / h264 (CQ=20): mean=97.522291, p5=94.391454
- clip3_typical / hevc (CQ=20): mean=97.466645, p5=94.546731
- clip3_typical / av1 (CQ=19): mean=98.314055, p5=95.818939
- clip4_diverse / h264 (CQ=20): mean=97.613579, p5=94.194779
- clip4_diverse / hevc (CQ=20): mean=97.567165, p5=94.17357
- clip4_diverse / av1 (CQ=19): mean=98.305411, p5=95.665916

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
