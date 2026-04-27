# VMAF Validation: v2.5 GPU Pipeline

**Status:** **FAIL** - per-codec offset adjustment required
**Date:** 2026-04-28 04:00
**ADR:** ADR-0007 D9
**Hardware:** RTX 4080 Laptop GPU (Ada Lovelace), driver 591.44
**FFmpeg:** ffmpeg version N-120402-g7c5319e692-20250729 Copyright (c) 2000-2025 the FFmpeg developers

## Pass Criterion (ADR-0007 D9)

- VMAF mean must be within +/- 2.0 of reference (i.e. >= 98.0)
- VMAF p5 (5th percentile) must be within +/- 3.0 of reference (i.e. >= 97.0)
- Both criteria must hold across all 3 codecs (h264_nvenc, hevc_nvenc, av1_nvenc)

## Test Parameters

- **CPU CRF:** 20
- **NVENC CQ:** 22 (CRF + 2 per ADR-0007 D3)
- **NVENC preset:** p4 (ADR-0007 D2 balanced default)
- **NVENC rate control:** vbr
- **NVENC b:v:** 0 (ADR-0007 D3 trap-avoid)
- **NVENC multipass:** 0 (ADR-0007 D7 default)
- **VMAF model:** vmaf_v0.6.1

## Reference Clips

- **clip1_motion:** `D:/render/1.mp4`
- **clip2_face:** `D:/render/13.mp4`
- **clip3_x3speed:** `D:/render\250918_174633_x3 CRF_2020-05-14_justmaiko_6826755271319145734_final.mp4`

## Results Table

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

## Per-Codec Summary

| Codec | Mean (avg of 3 clips) | p5 (worst of 3) | All Pass? |
|-------|----------------------|----------------|-----------|
| h264 | 98.40 | 93.66 | NO |
| hevc | 98.53 | 93.66 | NO |
| av1 | 99.23 | 95.84 | NO |

## Encode Performance

| Clip | Codec | CPU Time (s) | GPU Time (s) | Speedup | CPU Size (MB) | GPU Size (MB) |
|------|-------|--------------|--------------|---------|----------------|---------------|
| clip1_motion | h264 | 1.94 | 0.91 | 2.1x | 4.6 | 5.9 |
| clip1_motion | hevc | 6.11 | 0.75 | 8.1x | 5.1 | 5.8 |
| clip1_motion | av1 | 6.46 | 0.78 | 8.3x | 7.0 | 7.5 |
| clip2_face | h264 | 2.16 | 0.83 | 2.6x | 4.8 | 6.6 |
| clip2_face | hevc | 7.14 | 0.74 | 9.6x | 5.1 | 6.3 |
| clip2_face | av1 | 7.19 | 0.72 | 10.0x | 6.6 | 7.5 |
| clip3_x3speed | h264 | 1.6 | 0.7 | 2.3x | 4.9 | 5.4 |
| clip3_x3speed | hevc | 5.57 | 0.6 | 9.3x | 5.9 | 5.2 |
| clip3_x3speed | av1 | 5.27 | 0.63 | 8.4x | 7.9 | 6.6 |

## Verdict

**FAIL.** One or more codecs do not meet ADR-0007 D9 pass criteria. Per-codec offset adjustment required in core/preset_translator.py CRF_TO_CQ_OFFSET. Specific failures:

- clip2_face / h264: VMAF mean=98.784326, p5=96.02611, mean_pass=True, p5_pass=False
- clip2_face / hevc: VMAF mean=98.923298, p5=96.311361, mean_pass=True, p5_pass=False
- clip3_x3speed / h264: VMAF mean=98.007987, p5=93.657091, mean_pass=True, p5_pass=False
- clip3_x3speed / hevc: VMAF mean=98.004918, p5=93.657012, mean_pass=True, p5_pass=False
- clip3_x3speed / av1: VMAF mean=99.158115, p5=95.844874, mean_pass=True, p5_pass=False

Recommendation: lock per-codec rules in CRF_TO_CQ_OFFSET dict (e.g. h264:+2, hevc:+2, av1:+3) and re-run.

## Reproducibility

Per-pairing VMAF JSON logs and the aggregated `results.json` are retained at `benchmarks/_vmaf_work/` for inspection. The 18 encoded `.mp4` files (CPU references + GPU outputs, ~109 MB total) are gitignored — regenerable by re-running the orchestrator script (`/c/tmp/step4e_vmaf.py`) against the same reference clips on `D:/render/`.

All encodes used: `ffmpeg -i <input> -c:v <encoder> [-crf 20 | -cq:v 22 -rc:v vbr -b:v 0 -preset p4 -multipass 0] -c:a aac <output>`

VMAF measurement: `ffmpeg -i <gpu_out> -i <cpu_out> -filter_complex '[0:v][1:v]libvmaf=model=version=vmaf_v0.6.1:log_fmt=json' -f null -`
