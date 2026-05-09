# ADR-0007: GPU/NVENC pipeline architecture for auto_render.py (F3)

**Status:** Accepted

**Date:** 2026-04-27 (Proposed) — 2026-04-27 (Accepted, after commentary fill in Step 4a)

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

The subprocess+core_ffmpeg_runner path is mature, battle-tested across all 4 apps in the suite (auto_render, bench, merge, image_compress), and already handles the hard parts: cancel ladder via `_cancel_ffmpeg`, dual-dialect progress parsing (legacy stderr + `-progress pipe:1`), CRLF + UTF-8 stdout drain, hidden-window startupinfo on Windows.

Introducing QProcess for one feature creates a second async pattern in the codebase. Future maintainers (including future-me) would have to track two execution models — when GPU is enabled, when CPU is enabled, when one falls back to the other. That cognitive cost is real and recurring.

QProcess offers signal-based progress out of the box, but `core_ffmpeg_runner.run_ffmpeg(on_progress=...)` already wraps that semantically — callers don't see the subprocess.Popen seam. The "QProcess advantage" doesn't exist for our use case because the abstraction layer hides it.

Rejected alternative: porting the codebase to QProcess. Cost: refactor 4 apps to a new async pattern. Benefit: marginal. ADR-0007 D1 keeps subprocess.

### D2. NVENC preset family — p1 through p7

Use `-preset p4` as the default for "Balanced" tier; expose `p1`/`p7` for
"Max speed"/"Max quality" tiers. Always pair with `-tune hq` for offline
render workload. Legacy presets (`slow`/`hq`/`llhq`/`hp`) are forbidden.

The legacy preset names (`slow`/`hq`/`llhq`/`hp`) are formally deprecated by NVIDIA as of Video Codec SDK 10+ and driver R550 (Q1 2024). FFmpeg emits a runtime warning ("The selected preset is deprecated. Use p1 to p7 + -tune or fast/medium/slow") and NVIDIA has indicated removal in future driver releases. The p1-p7 numeric scale is the canonical interface.

p4 as default balances encode time and quality across all 3 NVENC families on RTX 4080. p1 (fastest) sacrifices ~3-5 VMAF points for 2-3× speed; p7 (slowest) gains ~1-2 VMAF points for 3-4× time cost. p4 is the sweet spot for "Balanced" tier and matches NVIDIA's reference recommendation in the Video Codec SDK 10 introduction.

Tune defaults to `hq` automatically when no tune is specified — we don't override it. The `ll` (low-latency) and `ull` (ultra-low-latency) tunes exist for streaming workloads where sub-frame latency matters, which doesn't apply to our offline batch render.

Per-codec preset behavior is similar enough at p4 across h264_nvenc, hevc_nvenc, and av1_nvenc that we don't need a per-codec lookup table — same default works.

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

The "+2" rule is the starting hypothesis, not a final answer. Multiple sources converge on +2 as the typical NVENC CQ ↔ CPU CRF perceptual offset for h264_nvenc on common content, but the actual offset varies measurably by codec (h264 ≈ +1-2, hevc ≈ +2-3, av1 ≈ +2-4) and by content complexity (high-motion content widens the gap, static content narrows it).

+2 is chosen as the universal default because (a) it's the median across published comparisons, (b) it's the value users coming from OBS/HandBrake will already expect, and (c) it gives a single rule for users to reason about — "GPU encoding shifts the quality dial up by 2."

The D9 VMAF validation gate is what makes this rule honest. We measure on RTX 4080 + current ffmpeg build before locking. If validation shows the +2 rule holds within ±2 VMAF mean / ±3 VMAF p5 across all three codecs, we ship universal +2. If h264 or hevc is fine but av1 needs +3 or +4, we lock per-codec — preserving simplicity where possible, accepting complexity where the perception-quality reality demands it.

What we don't do: ship +2 without validating, on the theory that "research-backed" is good enough. RTX 4080 + driver-as-installed + FFmpeg N-120402 build is a specific combination that hasn't been benchmarked in published research. The hour spent on D9 prevents the alternative — discovering 6 months in that all GPU presets ship at the wrong quality and users are silently paying for it.

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

H.264 is the default because it's the universally compatible baseline. Every device made in the last 15 years can play H.264. Every social platform accepts H.264 uploads without re-transcode warnings. Every editing tool ingests H.264. When users don't know what they need, H.264 is the correct answer.

HEVC is available but not default because the compression-efficiency gain (~30-40% smaller files at equivalent quality) only matters when storage or bandwidth is a real constraint. For most outputs, the gain isn't worth the playback-compatibility tax — Windows native HEVC playback requires a paid codec from the Microsoft Store, Android support is per-vendor, and some older browsers still don't decode HEVC. Users who know they need HEVC pick it; users who don't know default to safety.

AV1 ships with the "(experimental)" tag because AV1 in 2026 is in the same place HEVC was in 2018: encoder maturity exists (RTX 4080 drives av1_nvenc fine), but ecosystem support is incomplete. TikTok still rejects AV1 uploads as of early 2026. Instagram and Snapchat have partial support. YouTube transcodes AV1 input but originating in AV1 is non-canonical. Local playback works in VLC and modern browsers but not legacy software. The experimental tag manages user expectations: AV1 is not broken, but it might not work for the user's downstream pipeline, and that's a decision the user needs to opt into knowingly.

The dropdown architecture is the same regardless of which codec is the default. When AV1 social platform support catches up — likely 2027-2028 based on platform announcement cadence — promoting AV1 from "(experimental)" to "default" or HEVC to "default" is a one-line config change. We don't have to relitigate D4 to evolve the codec story.

Container choice mirrors the codec compatibility profile: H.264 and HEVC default to .mp4 because that's the universal container. AV1 defaults to .mkv because AV1-in-MP4 has compatibility quirks (some Apple platforms, some Windows codec packs) while AV1-in-MKV is unambiguously playable in VLC and modern browsers. Users who specifically need AV1-in-MP4 can override via Settings.

### D5. Fallback policy — silent CPU fallback on non-NVIDIA, explicit warning on NVENC failure

If `gpu_caps.nvenc_available == False` at startup, GPU toggle is disabled
in Settings (greyed out with hover tooltip "No NVIDIA GPU detected — CPU
encoding only"). Renders proceed via existing CPU path, no warning per
render.

If GPU toggle is enabled but NVENC encode FAILS at runtime (driver crash,
exhausted concurrent session limit, etc.), `RenderWorker` falls back to CPU
for that task with an explicit warning in the FFmpeg log + status row:
"GPU encode failed, retried on CPU." Batch continues.

The two halves of D5 deliberately differ in visibility because they reflect different user-actionability. When no NVIDIA hardware is detected at startup, the user can't fix that mid-session — surfacing the absence as a warning would be nagging about an unchangeable condition. The greyed-out toggle with hover tooltip ("No NVIDIA GPU detected — CPU encoding only") provides the information once, in context, when the user goes looking for the GPU setting. Subsequent renders just use CPU silently.

When NVENC is available but fails at runtime — driver hiccup, exhausted session count, VRAM pressure spike, transient issue with a specific encode — the user CAN investigate. So we surface it twice: in the FFmpeg log (for diagnostic detail) and in the per-task status row ("GPU encode failed, retried on CPU"). This is loud enough to notice when reviewing a completed batch, quiet enough not to interrupt a long unattended render.

We deliberately don't show a modal dialog on runtime fallback. Solo-user batch workflows often involve kicking off a long render and walking away. Coming back to a stuck dialog mid-batch is worse than coming back to a completed batch with status-row warnings the user can scroll through. The dialog-free design respects the unattended-batch use case.

The batch always continues. A failed task falls back to CPU and completes; subsequent tasks attempt GPU again (in case the failure was transient). We don't disable the GPU toggle for the rest of the session because most NVENC failures are transient — disabling on first failure would punish users for one bad task.

Hardware support spans the full NVIDIA range. NVENC works on any NVIDIA GPU from Maxwell (2014) forward; h264_nvenc and hevc_nvenc are universal across that range. av1_nvenc is RTX 40-series only (Ada generation hardware requirement). Users on older NVIDIA cards (GTX 10/16, RTX 20/30 series) see h264 + hevc in the codec dropdown working normally; the AV1 option either greys out at startup based on `gpu_caps` enumeration or, if attempted, surfaces D5's runtime fallback. Non-NVIDIA users (Intel, AMD, integrated graphics, no GPU) see the entire GPU toggle disabled per D5 startup-time path. The tool functions across the full hardware spectrum without per-tier configuration.

### D6. Concurrent NVENC sessions — limit to 2 by default

NVENC sessions cap at 2 simultaneous via `QSemaphore(2)` in the render
worker pool. Driver hard limit on 2025+ NVIDIA drivers is 12, but past 4
simultaneous sessions on consumer cards (RTX 4080 included), VRAM pressure
and quality degradation become noticeable.

Settings exposes the limit (1-6) as advanced/expert config; default 2.
1080p NVENC session ≈ 50MB VRAM, 4K ≈ 200-500MB.

The driver-imposed limit on consumer GeForce cards is currently 8 simultaneous NVENC sessions (as of NVIDIA driver 551.23, January 2024 — increased from the 2/3/5 progression of prior years). RTX 4080 specifically has dual NVENC encoders, which means it can drive multiple concurrent sessions with hardware-level parallelism rather than driver-level multiplexing.

2 as the default reflects solo-user workflow reality: the user is doing other things on the GPU (preview, scrubbing, occasionally unrelated apps), so leaving headroom matters. 2 simultaneous renders is enough to fully utilize encoder hardware on most preset chains because NVENC is rarely the bottleneck — disk I/O and ffmpeg's own demuxer/filter graph usually saturate first.

The 8 ceiling matches the actual driver limit on 2024+ consumer cards. Users on dedicated render boxes (RTX 4080+ with no other GPU workload) can legitimately push to 8 — RTX 4080's dual encoders make this realistic. We don't expose values above 8 because that's the driver hard limit on GeForce hardware.

Rejected: dynamic auto-detection based on VRAM. Implementation cost outweighs benefit when 2 covers 95% of the use cases and the manual ceiling covers the rest.

### D7. Multi-pass — single-pass default for CQ/VBR-CQ, multi-pass behind "Max quality" toggle

`multipass=0` (single-pass) by default. NVENC multi-pass primarily helps
CBR with bitrate targets — for CQ/VBR-CQ rate control (which we use), the
quality gain is marginal but encode time roughly doubles.

Expose `multipass=2` (full two-pass) only behind the Settings "Max quality"
button alongside p7 preset selection. Never expose `multipass=1`
(quarter-resolution pass) — minimal quality gain, real complexity cost.

NVENC multi-pass was designed for CBR with strict bitrate targets — the first pass collects scene complexity stats, the second pass distributes bits accordingly. For CQ/VBR-CQ rate control (which we use per D3), this analysis is largely wasted: CQ already targets per-block quality, so a "second pass" produces nearly identical output for ~2× the encode time.

The marginal quality gain on CQ is real but small (~0.5-1 VMAF point on hard content). For most users, single-pass at p4 produces output indistinguishable from multipass=2 at p4 in side-by-side blind testing.

multipass=1 (quarter-resolution analysis pass) is forbidden because it offers the encode-time cost of multi-pass with negligible quality gain over single-pass. It exists primarily for legacy CBR streaming workflows that don't apply here.

The "Max quality" toggle bundles multipass=2 + p7 + tune=hq into one user choice. Users who want maximum quality don't have to understand the three knobs separately — they get all three together. Users who want speed don't see the multipass option at all.

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

`core/config.py` already handles atomic write (write-temp + os.replace), utf-8 encoding (Bug 8 fix), and read-failure-with-defaults graceful degradation. F3 settings inherit all three for free.

Splitting GPU settings into a separate file would create a second config schema with the same atomicity, encoding, and migration concerns. No upside — only one application owns these settings.

The 6 keys (`gpu_enabled`, `gpu_codec`, `gpu_preset`, `gpu_max_concurrent`, `gpu_container_override`, `gpu_max_quality_mode`) are the minimum viable exposure for F3. Future additions (per-codec preset overrides, custom -cq:v values) can extend the same dict — no schema bump needed because we're using JSON dict access, not a strict schema like ADR-0006's preset format.

Default values are conservative: `gpu_enabled: false` (opt-in, no surprise GPU usage), `gpu_codec: "h264_nvenc"` (most universal), `gpu_preset: "p4"` (balanced default per D2), `gpu_max_concurrent: 2` (conservative per D6), `gpu_container_override: null` (use D4 codec defaults), `gpu_max_quality_mode: false` (single-pass per D7).

### D9. VMAF validation gate — required before tagging v2.5-complete

Before `tag v2.5-complete` lands (Step 5), VMAF validation must pass on
3 reference clips per codec (h264, hevc, av1) with `+2` CRF→CQ rule.
Results captured in `benchmarks/vmaf_validation_v2.5.md`.

If validation fails on any codec, lock per-codec rule before tagging.
If validation fails dramatically (>5 VMAF point delta), STOP and re-scope
F3 — the `+2` rule was research-backed but unverified on RTX 4080.

The CRF→CQ +2 rule (D3) is research-backed but unverified on this specific hardware (RTX 4080, NVIDIA driver as-installed, FFmpeg N-120402 build). Different hardware/driver/build combinations have shown ±1 point variance in CQ-to-CRF mapping in published benchmarks. Shipping a default that's 4 points off would mean every preset's "Quality" setting is calibrated wrong from day one.

3 reference clips per codec (h264, hevc, av1) is the minimum useful sample. The 3 clips should span: (1) high-motion content (action/sports), (2) slow-detail content (interview/static), (3) mixed dynamic range (tutorial-style with both). 9 encodes total. On RTX 4080, this completes in under 60 minutes including VMAF computation.

Pass criteria reflect the underlying perceptual reality: VMAF mean ±2 points is roughly the JND (just-noticeable-difference) threshold; ±3 on p5 (5th percentile) accounts for the worst-case frame in each clip. Tighter criteria (mean ±1, p5 ±2) would generate false positives from VMAF computation noise.

If validation fails on av1_nvenc specifically (most likely outcome — av1 is newer and less calibrated), lock per-codec rules: e.g., `+2` for h264/hevc, `+3` for av1. If validation fails dramatically (>5 VMAF point delta), the assumption of "linear CRF↔CQ mapping" is wrong and F3 needs re-scoping before ship.

Results captured in `benchmarks/vmaf_validation_v2.5.md` per Phase 1 methodology in `benchmarks/METHODOLOGY.md`. The benchmark is reproducible by re-running with the same clip set, so future hardware upgrades can re-validate the rule without redesigning the test.

Validation hardware vs supported hardware: D9 pins validation to RTX 4080 because we need a single reference platform to lock the +2 rule. The validation result extends directly to other Ada-generation cards (RTX 4060/4070/4080/4090) since they share the same NVENC silicon. For older NVIDIA GPUs, h264 and hevc validation results transfer (encoder ASIC behavior is consistent generation-over-generation for those codecs). The av1 rule is RTX 40-series-only because earlier cards lack av1_nvenc hardware entirely.

## Rationale

F3 was scoped under tight constraints that shaped every decision in this ADR. Solo dev capacity (no team to absorb a parallel architecture refactor), Windows + RTX 4080 as the primary development and VMAF-validation hardware (NVENC support extends back to Maxwell-generation GPUs from 2014; the tool runs on any NVIDIA GPU with `nvenc_available == True`, but D9 validation pins to RTX 4080 + current FFmpeg build to lock the perceptual quality rule on a single reference platform), system FFmpeg as the binary contract per ADR-0006, no PySide6 framework migration yet (Phase 2d work), and a PORT_NOTES timeline that has to land before further infrastructure work begins. The non-negotiable goal: add real GPU encoding value without expanding the maintenance surface or introducing a parallel async pattern that future-me has to track alongside the existing CPU path.

The 9 decisions hang together as three reinforcing groups. D1 and D8 minimize new architecture — F3 reuses the mature subprocess + core_ffmpeg_runner path and the existing core/config.py persistence layer rather than introducing QProcess or a new settings format. D2 through D6 lock the encoding parameters where research has already converged on a reasonable answer — p1-p7 preset family per NVIDIA Video Codec SDK 10, the CRF→CQ +2 hypothesis as the starting rule, the codec dropdown with H.264 default and AV1 experimental tag, the conservative concurrency limit, and the dual-mode fallback policy. D7 and D9 act as guard rails — single-pass as default keeps the user-facing performance fast, and the VMAF validation gate prevents the entire quality story from shipping broken if the +2 rule turns out to need per-codec adjustment.

The biggest unknown sits in D3 — specifically, whether the +2 CRF→CQ offset holds on av1_nvenc on RTX 4080 with the current FFmpeg build. Published research converges on +2 for h264_nvenc on common content, but av1_nvenc is newer and less calibrated, and content complexity widens the gap on high-motion material. D9's VMAF validation gate is what makes shipping F3 honest — we measure on the actual hardware before tagging v2.5-complete, lock per-codec rules if validation reveals divergence, and pause F3 entirely if the gap is dramatic. The hour spent on D9 is the cheapest insurance against the alternative — discovering 6 months in that GPU presets ship at the wrong quality and users have been silently paying for it.

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

**A5. Auto-promote AV1 to default when ecosystem catches up.** Considered. Rejected as automatic behavior; will be a manual D4 update in a future ADR (or supersession of ADR-0007) when social platform support reaches parity with H.264. The dropdown architecture supports this without code change — only the default value and the experimental tag move.

**A6. Per-codec custom CQ offsets in Settings UI.** Considered. Rejected for v2.5 to keep Settings dialog scope bounded. If D9 VMAF validation reveals codec-specific offsets are needed, they're hardcoded per-codec in the preset translator (D3) rather than user-configurable. Future ADR can promote to UI control if user demand surfaces.

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
