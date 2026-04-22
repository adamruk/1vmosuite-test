# NVENC Parameter Reference

**Scope:** Windows-only. NVIDIA NVENC encoders (`h264_nvenc`, `hevc_nvenc`, `av1_nvenc`) for preset authors working on 1vmo Suite.

**Audience:** the 3-of-5 Windows team members. Mac users (2-of-5) use VideoToolbox; can skip this doc.

**Not in scope:** CPU encoder reference (see ffmpeg docs), Mac VideoToolbox, AMD AMF, Intel QSV.

**Blocker awareness.** Observation V (codec-append gotcha) must ship fixed before NVENC presets work as authored. See `docs/ROADMAP.md`. Until then, NVENC presets are silently re-encoded as CPU libx264. Scheduled fix: Phase 2c-e Part A.

---

## NVENC generation matrix

NVENC is dedicated silicon, distinct from CUDA compute. Capabilities vary by GPU generation.

| Generation | GPUs | H.264 | HEVC 8 | HEVC 10 | AV1 | Notes |
|---|---|---|---|---|---|---|
| Kepler | GTX 600-700 | ✅ | ❌ | ❌ | ❌ | Legacy |
| Maxwell G1 | GTX 750/750 Ti | ✅ | ❌ | ❌ | ❌ | |
| Maxwell G2 | GTX 900 | ✅ | ✅ | ❌ | ❌ | HEVC introduced |
| Pascal | GTX 10 | ✅ | ✅ | ✅ | ❌ | 10-bit HEVC added |
| Turing | GTX 16, RTX 20 | ✅ | ✅ | ✅ | ❌ | Better quality; B-frame refs in HEVC |
| Ampere | RTX 30 | ✅ | ✅ | ✅ | ❌ | Further quality improvements |
| Ada | RTX 40 | ✅ | ✅ | ✅ | ✅ | **AV1 introduced.** Project dev machine is Ada. |
| Blackwell | RTX 50 | ✅ | ✅ | ✅ | ✅ | 4:2:2 chroma added |

**Reference:** [NVIDIA Video Encode/Decode GPU Support Matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new).

**Team notes.** 3 Windows teammates have NVENC-capable GPUs; specific generations should be confirmed per-person. Ampere+ preferred for preset parity. Ada-only features (AV1) fail with clear ffmpeg error on older cards — acceptable, fallback is the CPU variant of the same family. No team member has Blackwell as of 2026-04; stay on 4:2:0 chroma.

---

## Session and concurrency limits

Historical consumer-driver cap was 2 concurrent sessions (lifted to 3 in late 2022). **Current status (driver 522.25+, 2023 onward):** consumer cards get the same session limits as Quadro — effectively unlimited for single-user batch work.

**1vmo Suite rule.** Serialize NVENC encodes in the render queue. Don't spawn multiple concurrent NVENC processes — older drivers may still enforce caps.

---

## Encoder selection

| Encoder | Use when | Silicon requirement |
|---|---|---|
| `h264_nvenc` | Legacy compatibility targets (rare in 2026). Avoid when HEVC is an option — H.264 produces visibly larger files at matched quality. | Any NVENC generation |
| `hevc_nvenc` | **Primary recommendation for 1vmo Suite Windows output.** Modern platforms (YouTube, Vimeo, Twitch) support HEVC upload. ~40-50% smaller files than H.264 at matched visual quality. Every Mac from ~2017 and every iPhone 6+ plays HEVC. | Maxwell Gen 2+ |
| `av1_nvenc` | YouTube/Netflix backend AV1 support. When file size matters extremely. **Treat as experimental** — fewer stress-tested pipelines than HEVC. | **Ada (RTX 40) or newer** |

---

## Key parameters

NVENC uses a partially different vocabulary from CPU encoders. Don't assume libx264 knowledge translates.

### `-preset` (p1-p7 speed/quality scale)

| Preset | Alias | Meaning |
|---|---|---|
| `p1` | `fastest` | Highest speed, lowest quality |
| `p4` | `medium` | Balanced — default |
| `p5` | `slow` | |
| `p6` | `slower` | |
| `p7` | `slowest` | Highest quality, lowest speed |

**1vmo Suite recommendation.** Default `p5` or `p6` for shipped presets. `p7` for "archive quality" presets. `p3`/`p4` for "fast iteration." Avoid `p1`/`p2` in shipped presets — quality loss is visible.

### `-tune`

`hq` (high quality — use this), `ll` (low latency — streaming only), `ull` (ultra-low latency — streaming only), `lossless`.

**1vmo Suite.** Always `hq` for offline rendering.

### `-rc` (rate control)

| Mode | Use for |
|---|---|
| `vbr` | **Default.** Variable bitrate, target average, allow bursting. |
| `cbr` | Streaming only, not files. |
| `constqp` | Direct QP control for specific quality targets. |
| `vbr_hq` / `cbr_hq` | **Deprecated legacy aliases.** Use `-rc vbr -preset p6` instead. |

**1vmo Suite.** `vbr` paired with `-cq` (constant quality) below.

### `-cq` (constant quality)

0-51 scale, lower = better. Analogous to libx264 CRF but not identical semantics.

**Transparent quality bands** (visually lossless or near-lossless, on driver 520+ / ffmpeg 7.x+):

| Codec | Band |
|---|---|
| `h264_nvenc` | CQ 21-24 |
| `hevc_nvenc` | CQ 19-23 |
| `av1_nvenc` | CQ 28-32 (AV1 scale differs) |

**1vmo Suite targets.** High quality: CQ 19 (HEVC) / 22 (H.264). Balanced: CQ 22 / 24. Fast/small: CQ 26 / 28. AV1: start 30, tune 28-34.

### `-multipass`

| Value | Meaning |
|---|---|
| `disabled` | Single pass — default |
| `qres` | **Recommended.** Quarter-resolution first pass, full second. Minimal speed hit, measurable quality gain. |
| `fullres` | Full-resolution both passes. Archive-only. |

### `-spatial_aq`, `-temporal_aq`, `-aq-strength`

Adaptive quantization — more bits to perceptually important regions. `-spatial_aq 1` / `-temporal_aq 1` are safe defaults for all 1vmo Suite presets. Leave `-aq-strength` at default 8.

### `-rc-lookahead`

Frames looked ahead for rate-control decisions. Max typically 32.

**1vmo Suite.** `-rc-lookahead 32` for offline encodes. Quality gain real; latency cost irrelevant for file rendering.

### `-b_ref_mode`

`each` (each B-frame can be referenced), `middle`, `disabled`.

**1vmo Suite.** `each` for Turing+ (B-frame referencing supported). Improves compression.

### `-weighted_pred`

**Caution.** `-weighted_pred 1` + B-frames on **H.264** produces broken output on some driver versions. HEVC is fine.

**1vmo Suite.** Enable only for HEVC presets. Leave off for H.264 unless B-frames are also disabled.

### `-pix_fmt` (required on every preset)

| Encoder | Required format |
|---|---|
| `h264_nvenc` 8-bit | `yuv420p` |
| `hevc_nvenc` 8-bit | `yuv420p` |
| `hevc_nvenc` 10-bit Main10 | `p010le` or `yuv420p10le` |
| `av1_nvenc` 8-bit | `yuv420p` |
| `av1_nvenc` 10-bit | `p010le` |

**Authoring rule.** Always specify `-pix_fmt` explicitly. Silent fallback to wrong format causes silent downstream compatibility issues.

Note: `h264_nvenc` High 10-bit has inconsistent driver support — avoid.

### `-forced-idr`

`-forced-idr 1` forces IDR frames at keyframe intervals, improving seekability. Use for presets targeting editing or streaming pipelines.

---

## Preset template

All NVENC presets follow this structure. Variation is in the codec identifier and target values.

```
-c:v {codec}
-preset {preset}
-tune hq
-rc vbr
-cq {cq}
-multipass qres
-spatial_aq 1
-temporal_aq 1
-rc-lookahead 32
-b_ref_mode each
{weighted_pred}
-pix_fmt {pix_fmt}
-c:a {audio_codec}
-b:a {audio_bitrate}
```

### Variation table

| Template | codec | preset | cq | weighted_pred | pix_fmt | audio_codec | audio_bitrate |
|---|---|---|---|---|---|---|---|
| **HEVC high quality (archive)** | `hevc_nvenc` | `p7` | `19` | `-weighted_pred 1` | `yuv420p` | `aac` | `192k` |
| **HEVC balanced (default rec)** | `hevc_nvenc` | `p5` | `22` | *omit* | `yuv420p` | `aac` | `160k` |
| **H.264 compatibility** | `h264_nvenc` | `p5` | `23` | *omit* | `yuv420p` | `aac` | `160k` |
| **AV1 (Ada+ only)** | `av1_nvenc` | `p6` | `30` | *omit* | `yuv420p` | `libopus` | `128k` |

**Important.** These templates will not render correctly until Observation V ships fixed. Do not add NVENC presets to `encoder.builtin.json` before Phase 2c-e Part A lands.

---

## Hardware-accelerated decode pairing

For max throughput, pair NVENC with NVDEC:

```
-hwaccel cuda -hwaccel_output_format cuda -i <input> ... -c:v hevc_nvenc ...
```

Frames stay in GPU memory through the whole pipeline. Substantial throughput gain for batch re-encodes.

**Caveat.** Filter chains requiring CPU-side processing (most `-filter_complex` operations) break the GPU-only pipeline. With a filter chain present, drop `-hwaccel cuda -hwaccel_output_format cuda` and let CPU filtering run at native speed, then re-upload to GPU for encoding (`hwupload_cuda`) — or use GPU-native filter equivalents, which is complex and rarely worth it.

**1vmo Suite rule.** Pair NVDEC+NVENC only for straight-through re-encodes. For filter-graph presets (Ultimate, Zoom), don't pair — CPU filtering is fine.

---

## Verification and debugging

### Probe NVENC availability

```
ffmpeg -hide_banner -encoders | grep nvenc
```

Absence = driver or ffmpeg build problem, not a preset problem.

### Quality comparison

Modern NVENC (Ampere+) at `p6`/`p7` often matches or exceeds libx264 `-preset slow`. Don't assume NVENC is lower quality by default.

### Common failures

| Error | Cause |
|---|---|
| "No capable devices found" | Driver missing or GPU doesn't support requested codec |
| "OpenEncodeSessionEx failed" | Session limit hit (rare on modern drivers) |
| Silent CPU fallback | Observation V unfixed — verify output with `ffprobe` |

---

## References

- [NVIDIA Video Encode/Decode GPU Support Matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new)
- [NVIDIA NVENC Video Codec SDK Docs](https://docs.nvidia.com/video-technologies/video-codec-sdk/)
- [FFmpeg H.264 NVENC options](https://ffmpeg.org/ffmpeg-codecs.html#Options-8)
- [rigaya's NVEncC](https://github.com/rigaya/NVEnc) — alternative wrapper exposing deeper parameters; useful reference for what ffmpeg doesn't surface directly.
- See also: `PRESET_PHILOSOPHY.md` (when to use NVENC vs CPU), `ROADMAP.md` (Observation V status), `PHASE_2C_PLAN.md` (Observation V fix schedule).

---

## Maintenance

Stable document. Updates when: NVIDIA ships a new generation, FFmpeg adds/removes NVENC parameters, Observation V ships fixed, or a new codec joins NVENC.

Audit trail: `git log docs/NVENC_PARAMETER_REFERENCE.md`.