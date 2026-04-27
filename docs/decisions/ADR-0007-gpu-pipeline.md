# ADR-0007: GPU/NVENC pipeline architecture for auto_render.py (F3)

**Status:** Proposed

**Date:** 2026-04-27

**Decision makers:** Adam (project lead)

**Supersedes:** none

**Amends:** none

## Context

Phase 2.5 feature F3 introduces hardware-accelerated encoding via NVIDIA NVENC
to `auto_render.py`. The v2 baseline has GPU detection (`gpu_detect.py`,
344 lines) wired into `auto_render` startup — the statusbar shows GPU caps,
double-click pops a detailed report — but `RenderWorker.process()` does NOT
yet branch on `use_gpu`. All renders currently go through CPU
(libx264/libx265) via `core_ffmpeg_runner.run_ffmpeg(...)` (subprocess.Popen
with progress parsing and cancel handling).

System ffmpeg (C:/ffmpeg/bin/ffmpeg, build N-120402-g7c5319e692-20250729)
exposes h264_nvenc, hevc_nvenc, av1_nvenc — all 3 NVENC families compiled in
with libvmaf available for validation. RTX 4080 supports the full p1-p7
preset family (deprecated `slow`/`hq`/`llhq`/`hp` legacy presets must NOT be
used; they emit runtime warnings on modern drivers).

Reference docs already in repo:

- `docs/NVENC_PARAMETER_REFERENCE.md` — NVENC generation matrix, encoder
  capability table
- `FFMPEG_CPU_TO_NVENC_REFERENCE.md` — CPU encoder → NVENC encoder mapping
  with rate-control translation notes
- `docs/PRESET_PHILOSOPHY.md` — preset authoring guidelines
- `benchmarks/METHODOLOGY.md` — wall-clock + size + VMAF measurement
  methodology (Phase 1 infrastructure)

This ADR locks the architectural decisions that shape F3 implementation:
preset translation strategy, codec dropdown contents, default container,
fallback policy, concurrency, multi-pass behavior, settings persistence, and
the CRF→CQ rate-control rule.

## Decision

### D1. Subprocess + core_ffmpeg_runner — keep, do NOT introduce QProcess

Render path stays on `subprocess.Popen` via `core_ffmpeg_runner.run_ffmpeg`.
QProcess is NOT introduced.

[COMMENTARY PLACEHOLDER — Adam: rationale for keeping subprocess. Suggested
talking points: core_ffmpeg_runner is mature (Phase 2a/5b extraction), used
by all 4 apps, has cancel ladder + progress parsing already; introducing
QProcess for one feature creates a second async pattern in the codebase;
QProcess offers signal-based progress but core_ffmpeg_runner already wraps
that for us. The cost of NOT switching is minimal — we still get GPU work
through the existing path.]

### D2. NVENC preset family — p1 through p7

Use `-preset p4` as the default for "Balanced" tier; expose `p1`/`p7` for
"Max speed"/"Max quality" tiers. Always pair with `-tune hq` for offline
render workload. Legacy presets (`slow`/`hq`/`llhq`/`hp`) are forbidden.

[COMMENTARY PLACEHOLDER — Adam: any nuance on preset selection per codec?
h264_nvenc and hevc_nvenc behave similarly; av1_nvenc has different
sweet-spot behavior. Default to p4 for all 3 unless we have hardware data
suggesting otherwise.]

### D3. CRF → CQ mapping — `+2` rule, validate per codec via VMAF before locking

Translation: `CQ_value = CRF_value + 2`. A preset specifying `-crf 20`
becomes `-cq:v 22 -rc:v vbr -b:v 0` for NVENC. The `-b:v 0` is critical to
avoid the NVENC bitrate-target trap.

This rule must be validated per codec on RTX 4080 hardware before locking
as production default. Validation methodology:

```bash
# Reference encode (CPU CRF 20)
ffmpeg -i ref.mp4 -c:v libx264 -crf 20 ref_cpu.mp4

# NVENC test (CQ 22)
ffmpeg -i ref.mp4 -c:v h264_nvenc -preset p4 -tune hq -cq:v 22 -rc:v vbr -b:v 0 nvenc_test.mp4

# VMAF compare
ffmpeg -i nvenc_test.mp4 -i ref_cpu.mp4 -lavfi libvmaf="log_path=vmaf.json" -f null -
```

Pass criterion: VMAF mean delta within ±2 points; VMAF p5 (5th percentile)
within ±3 points. If `+2` fails on av1_nvenc, lock per-codec rule
(e.g., `+2` h264, `+2` hevc, `+3` av1).

[COMMENTARY PLACEHOLDER — Adam: VMAF runs are quick on a 30s reference
clip. Recommend running before Phase 2.5b lands so the rule is locked
before users see the GPU toggle. Validation lives in benchmarks/.]

### D4. Codec dropdown — h264 default, hevc available, av1 marked "(experimental)"

Settings dialog GPU codec selector:

| Label | FFmpeg encoder | Default container | Status |
|---|---|---|---|
| H.264 (NVENC) — fast, universal | h264_nvenc | mp4 | default |
| HEVC (NVENC) — smaller files | hevc_nvenc | mp4 | available |
| AV1 (NVENC) — smallest, experimental | av1_nvenc | mkv | experimental |

AV1 default container is MKV (better AV1 ecosystem support); H.264/HEVC
default to MP4 (most familiar, widest playback). Container choice surfaces
in Settings as overrideable.

[COMMENTARY PLACEHOLDER — Adam: AV1 "(experimental)" tag is real — many
social platforms still reject AV1 uploads as of 2026. If your target is
content creators uploading to TikTok/Instagram, default to HEVC. If
target is local archive, default to AV1.]

### D5. Fallback policy — silent CPU fallback on non-NVIDIA, explicit warning on NVENC failure

If `gpu_caps.nvenc_available == False` at startup, GPU toggle is disabled
in Settings (greyed out with hover tooltip "No NVIDIA GPU detected — CPU
encoding only"). Renders proceed via existing CPU path, no warning per
render.

If GPU toggle is enabled but NVENC encode FAILS at runtime (driver crash,
exhausted concurrent session limit, etc.), `RenderWorker` falls back to CPU
for that task with an explicit warning in the FFmpeg log + status row:
"GPU encode failed, retried on CPU." Batch continues.

[COMMENTARY PLACEHOLDER — Adam: distinguish "no NVIDIA hardware" (silent
CPU) from "NVIDIA hardware present but NVENC failed" (explicit fallback
warning). The distinction matters because the first is expected on
non-NVIDIA machines; the second is a real anomaly worth surfacing.]

### D6. Concurrent NVENC sessions — limit to 2 by default

NVENC sessions cap at 2 simultaneous via `QSemaphore(2)` in the render
worker pool. Driver hard limit on 2025+ NVIDIA drivers is 12, but past 4
simultaneous sessions on consumer cards (RTX 4080 included), VRAM pressure
and quality degradation become noticeable.

Settings exposes the limit (1-6) as advanced/expert config; default 2.
1080p NVENC session ≈ 50MB VRAM, 4K ≈ 200-500MB.

[COMMENTARY PLACEHOLDER — Adam: 2 is the safe default. Expose 6 as the
expert ceiling because 4 is the realistic consumer-card limit and 6 gives
a small headroom buffer for users who know their hardware.]

### D7. Multi-pass — single-pass default for CQ/VBR-CQ, multi-pass behind "Max quality" toggle

`multipass=0` (single-pass) by default. NVENC multi-pass primarily helps
CBR with bitrate targets — for CQ/VBR-CQ rate control (which we use), the
quality gain is marginal but encode time roughly doubles.

Expose `multipass=2` (full two-pass) only behind the Settings "Max quality"
button alongside p7 preset selection. Never expose `multipass=1`
(quarter-resolution pass) — minimal quality gain, real complexity cost.

[COMMENTARY PLACEHOLDER — Adam: keep multipass behind a single button so
users don't have to understand it. "Max quality" implies p7 + multipass=2
+ tune=hq.]

### D8. Settings persistence — JSON via core/config.py, atomic write

GPU pipeline settings live in the existing `config_video_renderer.json`
(via `core/config.py`). New keys:

```json
{
  "gpu_enabled": false,
  "gpu_codec": "h264_nvenc",
  "gpu_preset": "p4",
  "gpu_max_concurrent": 2,
  "gpu_container_override": null,
  "gpu_max_quality_mode": false
}
```

Atomic write via existing `core/config.py` write pattern (write-temp +
os.replace). On read failure, log + use defaults; do NOT crash.

[COMMENTARY PLACEHOLDER — Adam: piggybacking on core/config.py keeps
Settings-dialog implementation cheap and inherits the utf-8 fix from
Bug 8. No new file format.]

### D9. VMAF validation gate — required before tagging v2.5-complete

Before `tag v2.5-complete` lands (Step 5), VMAF validation must pass on
3 reference clips per codec (h264, hevc, av1) with `+2` CRF→CQ rule.
Results captured in `benchmarks/vmaf_validation_v2.5.md`.

If validation fails on any codec, lock per-codec rule before tagging.
If validation fails dramatically (>5 VMAF point delta), STOP and re-scope
F3 — the `+2` rule was research-backed but unverified on RTX 4080.

[COMMENTARY PLACEHOLDER — Adam: this is the gate that prevents shipping
a broken quality default. 3 clips × 3 codecs = 9 encodes, runs in under
an hour on RTX 4080.]

## Rationale

[COMMENTARY PLACEHOLDER — Adam: 2-3 paragraphs synthesizing why these 9
decisions hang together. Suggested narrative arc:

1. The constraint set is tight: solo dev, Windows + RTX 4080 baseline,
   PORT_NOTES timeline, no PySide6 yet. F3 must add real GPU value
   without expanding the maintenance surface.

2. Decisions D1 + D8 minimize new architecture (reuse subprocess, reuse
   config.py). D2-D6 lock the encoding parameters research already
   converged on (p1-p7, +2 rule, codec dropdown). D7 + D9 are guard rails:
   single-pass keeps the default fast; VMAF gate prevents shipping
   broken quality.

3. The single biggest unknown is D3 (CRF→CQ +2 rule on av1_nvenc
   specifically). VMAF validation closes that loop.]

## Consequences

**Positive:**

- F3 implementation surface is bounded (~200-300 LOC in auto_render.py +
  ~50 LOC in core/ffmpeg_runner.py for the preset translator)
- Single subprocess pattern preserved across 4 apps + GPU pipeline
- Settings format is utf-8-safe (inherits Bug 8 fix)
- VMAF gate prevents quality regression at v2.5-complete
- AV1 dropdown entry is future-proof; experimental tag manages user
  expectations

**Negative / costs:**

- VMAF validation is a hard prerequisite before tagging v2.5-complete
  (cannot skip; cannot defer to post-tag)
- AV1 in dropdown adds a support surface even with experimental tag —
  user reports of "AV1 doesn't play on my phone" become real
- Multi-pass behind "Max quality" toggle is one more UI element to
  maintain across PySide6 migration in Phase 2d

**Neutral:**

- Concurrent NVENC limit of 2 is conservative; users on 4090s may want
  more — exposed as advanced setting

## Alternatives considered

**A1. QProcess instead of subprocess.** Rejected per D1 — would create a
second async pattern alongside the existing core_ffmpeg_runner.

**A2. Bundle FFmpeg with installer instead of system FFmpeg.** Rejected —
~150 MB installer cost, plus version-pinning headaches when ffmpeg
upstream changes NVENC behavior. Per ADR-0006, system FFmpeg is the
v2 contract.

**A3. Separate Settings file for GPU config.** Rejected per D8 — no value
in splitting config_video_renderer.json across 2 files.

**A4. Defer av1_nvenc to Phase 3.** Considered. Decision: include in
dropdown with "(experimental)" tag rather than exclude entirely. Reasons:
(a) build supports it, (b) early adopters benefit, (c) experimental
tag manages expectations, (d) dropdown architecture is the same whether
av1 is included or not. Trivial to remove later if support burden
materializes.

[COMMENTARY PLACEHOLDER — Adam: any other alternatives worth recording
for posterity?]

## References

- docs/NVENC_PARAMETER_REFERENCE.md — NVENC generation matrix + capability table
- FFMPEG_CPU_TO_NVENC_REFERENCE.md — CPU encoder → NVENC encoder mapping
- docs/PRESET_PHILOSOPHY.md — preset authoring principles
- benchmarks/METHODOLOGY.md — VMAF measurement methodology
- docs/PHASE_2_PORT_NOTES.md — F3 scope and PORT_NOTES context
- ADR-0001 — manual-smoke testing methodology (F3 follows; no pytest exception)
- ADR-0006 — JSON schema versioning pattern (informs Settings persistence)
- NVIDIA Video Codec SDK 10+ documentation (external)

## Related

- ADR-0001 (manual-smoke methodology — F3 follows without exception)
- ADR-0006 (schema versioning — informs settings persistence pattern)
