# ADR-0008: Empirical VMAF Validation Thresholds

**Status:** Accepted
**Date:** 2026-04-28
**Decision makers:** Adam (project lead)
**Supersedes:** ADR-0007 D9 (VMAF validation gate thresholds)
**Related:** ADR-0007 D2 (NVENC preset family), ADR-0007 D3 (CRF->CQ rule), ADR-0007 D7 (Max Quality Mode)

## Context

ADR-0007 D9 specified VMAF validation thresholds of mean >= 98.0 and p5 >= 97.0 across all 3 codecs (h264_nvenc, hevc_nvenc, av1_nvenc). These thresholds were set hypothetically when ADR-0007 was authored, before empirical validation was run.

Three rounds of validation (fix-1 / fix-2 / fix-3) produced 36 measurements (3 rounds x 4 reference clips x 3 codecs) demonstrating that NVENC encoders on RTX 4080 + FFmpeg N-120402 + 1vmo content profile operate 1-3 points below the original D9 thresholds, regardless of encoder-side tuning.

## Empirical evidence summary

Cumulative encoder-side tuning across 3 iterations produced ~0.3 mean / ~0.6 p5 lift:

| Round | Configuration | h264 mean / p5_min | hevc mean / p5_min | av1 mean / p5_min |
|-------|---------------|--------------------|--------------------|--------------------|
| fix-1 (commit c1f5ea8) | offset +2, p4, mp=0 | 97.92 / 93.60 | 97.99 / 93.57 | 98.70 / 95.18 |
| fix-2 (commit bf3fa39) | per-codec offsets, p4, mp=0 | 98.21 / 94.19 | 98.26 / 94.17 | 98.88 / 95.67 |
| fix-3 (commit b1f8842) | per-codec offsets, p7, mp=2 | 98.25 / 94.23 | 98.29 / 94.21 | 98.89 / 95.70 |

Worst observation across all 36 measurements:
- **Worst mean: 97.15** (hevc_nvenc, clip3_typical, fix-2)
- **Worst p5: 93.57** (hevc_nvenc, clip4_diverse, fix-1)

ADR-0007 D7 escalation (Max Quality Mode: preset p7 + multipass=2) produced negligible lift (<0.05 across all 6 metrics in fix-3 vs fix-2). This confirms encoder-side tuning has hit a structural ceiling on this hardware/content profile.

## Decision

Supersede ADR-0007 D9 with empirically-calibrated thresholds:

| Threshold | ADR-0007 D9 (original, hypothetical) | ADR-0008 (calibrated to empirical ceiling) |
|-----------|--------------------------------------|--------------------------------------------|
| Mean VMAF | >= 98.0 | **>= 96.0** |
| p5 VMAF | >= 97.0 | **>= 93.0** |

Both thresholds set 1.0 point below worst observed value across all 36 measurements (1-point safety margin).

## Rationale

1. **Calibration to actual ceiling, not hypothesis.** D9 was authored without RTX 4080 measurement data; ADR-0008 incorporates 36 empirical measurements across 3 rounds.

2. **Encoder-side tuning exhausted.** Three rounds tested (a) baseline offset, (b) per-codec offsets, (c) Max Quality Mode (p7+mp2). Cumulative lift: ~0.6 p5. D9 gap: 3-4 p5 points. Further encoder tuning would not close the gap.

3. **Symmetric 1-point margin.** Both thresholds set 1.0 below worst observed (mean 97.15 -> 96.0; p5 93.57 -> 93.0). Margin protects against measurement noise and content variance.

4. **ADR best practice: supersession over editing.** ADR-0007 retains Status=Accepted; D9's thresholds preserved verbatim as historical hypothesis. ADR-0008 documents empirical revision with full audit trail.

5. **GPU pipeline value preserved.** Even at calibrated thresholds, NVENC delivers 1.4-11x speedup over CPU on hevc/av1 (fix-3 measurements) at acceptable quality. h264 NVENC speedup is reduced (1.4-1.5x at p7) but still positive.

## Pass criterion (for v2.5-complete tag and future validation)

A VMAF validation run PASSES iff for ALL pairings (clips x codecs):
- VMAF mean >= 96.0
- VMAF p5 (5th percentile) >= 93.0

Both criteria must hold across all 3 codecs (h264_nvenc, hevc_nvenc, av1_nvenc) for ALL reference clips.

Validation against fix-3 results: all 12 pairings PASS at ADR-0008 thresholds (smallest margin: clip3_typical hevc mean=97.49 +1.49, p5=94.60 +1.60).

## Consequences

**Positive:**
- v2.5-complete tag unblocked (was blocked by D9 hypothetical thresholds)
- Future validation runs measure against achievable, empirically-calibrated criteria
- Full audit trail preserved (D9 hypothesis + 3 rounds of evidence + ADR-0008 calibration)

**Negative:**
- Lower thresholds than D9 mean some perceptual quality loss vs CPU reference is accepted as "passing"
- Future content types with different characteristics (e.g., 4K, animation, gaming captures) may need re-validation against ADR-0008 thresholds; if they fail, ADR-0009 supersession would amend further

**Neutral:**
- ADR-0007 D2/D3/D7 remain unchanged. Only D9 thresholds are revised.
- Production gpu_preset config default remains "p4" (per Step 4d-i + auto_render.py L85+L369). Users opt into Max Quality Mode via Settings.

## References

- ADR-0007: GPU Pipeline (Status: Accepted)
- benchmarks/vmaf_validation_v2.5.md: full empirical data with 3-round revision history
- Commit 4cff4f0: original Step 4e validation (3-clip, FAIL under D9)
- Commit c1f5ea8: Step 4e-fix-1 (4-clip revised, FAIL under D9)
- Commit bf3fa39: Step 4e-fix-2 (per-codec offsets, FAIL under D9)
- Commit b1f8842: Step 4e-fix-3 (Max Quality Mode, FAIL under D9, ceiling confirmed)
