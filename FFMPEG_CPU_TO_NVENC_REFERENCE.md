# FFmpeg: CPU → NVIDIA NVENC GPU Encoding Reference

Consolidated technical notes on migrating an FFmpeg pipeline from CPU software encoders (libx264 / libx265 / libaom-av1 / libsvtav1) to NVIDIA NVENC hardware encoders (h264_nvenc / hevc_nvenc / av1_nvenc). Empirically verified where marked; spec-level otherwise. Use as a starting point, not a substitute for current NVIDIA Video Codec SDK docs.

---

## 1. Why migrate — tradeoff summary

NVENC trades absolute quality-per-bit for wall-clock throughput. A 10-minute 4K encode that takes 8 minutes on libx265 `medium` can take 30–90 seconds on hevc_nvenc with comparable (not identical) visual quality. Expected file-size/quality gap vs libx264/libx265 at matched-quality targets is typically 10–25% larger file at equal visual quality, narrower on recent (Ada) silicon than older generations.

NVENC wins on:
- Throughput for large batches
- CPU contention (frees cores for other work)
- Power efficiency per encoded second

libx264/libx265 still win on:
- Absolute encode efficiency at slow presets (`veryslow`, `placebo`)
- Fine-grained rate control (2-pass VBR with strict bitrate targeting)
- Encoder maturity around edge cases (odd frame sizes, unusual chroma)

---

## 2. NVENC hardware capability matrix

NVENC silicon blocks are generation-gated by codec. Critical to check before committing a pipeline to a given codec:

| Generation | GPU family | H.264 enc | HEVC enc | AV1 enc |
|---|---|---|---|---|
| Turing | RTX 20xx, GTX 16xx | ✓ | ✓ | ✗ |
| Ampere | RTX 30xx, A-series | ✓ | ✓ | ✗ (decode only) |
| Ada Lovelace | RTX 40xx | ✓ | ✓ | ✓ |
| Blackwell | RTX 50xx | ✓ | ✓ | ✓ |

Consumer laptop chips generally carry a single NVENC block. Workstation/server boards (some A-series, xx90-class) may carry multiple — relevant for concurrent session limits.

Concurrent session limits: consumer drivers historically cap NVENC sessions per host (lifted via unofficial driver patches, not production-safe). Check current NVIDIA driver release notes for the effective cap on your target driver version.

---

## 3. Encoder name mapping

| CPU encoder | NVENC equivalent |
|---|---|
| libx264 | h264_nvenc |
| libx265 | hevc_nvenc |
| libaom-av1 / libsvtav1 | av1_nvenc |

Verify encoder availability on a given build:
```
ffmpeg -encoders | findstr nvenc   # Windows
ffmpeg -encoders | grep nvenc      # Linux/macOS
```

Per-encoder parameter reference:
```
ffmpeg -h encoder=hevc_nvenc
```

---

## 4. Rate control / quality parameter translation

CPU CRF and NVENC CQ are **different scales** despite looking similar. Do not treat a `-crf 18` target as equivalent to `-cq 18`.

- libx264/libx265: `-crf <n>` where lower = better, 18 ≈ visually lossless for H.264, 20–22 typical for HEVC.
- NVENC: `-cq <n>` on a 0–51 scale, lower = better. 19–23 is the common visually-transparent band for hevc_nvenc on recent drivers.

Preset naming also differs:
- libx264/libx265: `ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo`
- NVENC: `p1` (fastest, lowest quality) through `p7` (slowest, highest quality). `p5`–`p7` is the practical quality range; `p1`–`p3` are for real-time / low-latency use cases.

Additional NVENC quality levers without direct CPU equivalents:
- `-tune hq | ll | ull | lossless` — high-quality, low-latency, ultra-low-latency, lossless
- `-rc vbr | cbr | constqp` — rate control mode
- `-multipass disabled | qres | fullres` — NVENC's equivalent to 2-pass, available on Turing+

---

## 5. Pixel format / chroma subsampling constraints

**4:4:4 chroma (yuv444p, yuv444p10le):**
- `av1_nvenc` hardware-rejects 4:4:4 inputs. FFmpeg's NVENC AV1 code path selects profile based on source pix_fmt; the driver returns an error before encoding starts. This is a hardware-level constraint, not a bug.
- `h264_nvenc` and `hevc_nvenc` silently accept 4:4:4 input and produce downstream-incompatible output on most players and NLEs. No warning. Catch these at pipeline validation; convert upstream with:
  ```
  ffmpeg -i INPUT -vf format=yuv420p -c:v libx264 -preset ultrafast -crf 0 intermediate.mkv
  ```

**10-bit pix_fmts (yuv420p10le, p010le, yuv422p10le):**
- Supported in `hevc_nvenc` (Main10 profile) and `av1_nvenc`.
- NOT supported in `h264_nvenc` (H.264 High 10 is spec-level but NVENC silicon doesn't implement it).
- Driver requires correct pix_fmt at encoder input. For 10-bit HEVC, `p010le` is the native hardware format.

**HBD (higher bit depth) inputs through hwaccel:**
If decoding on GPU with `-hwaccel cuda` and the output pix_fmt is 10-bit, frames live in GPU memory in a hardware-specific layout. CPU-side filters (most of FFmpeg's `-vf` chain) cannot read this layout directly. Insert an explicit download:
```
-vf hwdownload,format=nv12,format=<target_pix_fmt>
```
Without this, 10-bit encodes through a GPU-decode → software-filter → NVENC-encode chain can fail with a memory-boundary error. The filter materializes the frame into CPU memory before the filter chain touches it.

---

## 6. Known NVENC parameter pitfalls (empirical)

These are **not** clearly documented with warnings in official NVENC parameter references. Verified through empirical VMAF testing and community bug reports. Driver-version-sensitive — verify against the specific driver you're targeting.

### H.264 (h264_nvenc)
- `weighted_pred=1` + `bf>0` produces silent visually-broken output. No error, no warning. Choose one or the other.
- `b_ref_mode=each` is **not valid in the H.264 spec**. Use `b_ref_mode=disabled` or `b_ref_mode=middle`. NVENC will accept the argument but emit non-compliant output.

### HEVC (hevc_nvenc)
- `b_ref_mode=middle` requires `refs>=3` (DPB size constraint). Below 3 reference frames, the middle mode silently falls back with unpredictable quality impact.
- `b_ref_mode=middle` on NVIDIA driver 525+ drops VMAF approximately 0.7 vs `b_ref_mode=each`. For HEVC archival-quality use cases on recent drivers, prefer `each`.

### AV1 (av1_nvenc)
- Profile selection is hardcoded to `main` based on source pix_fmt at the FFmpeg NVENC source level. AV1 presets that attempt to specify alternate profiles (`high`, `professional`) on hardware that doesn't support them will fail opaquely. Keep `profile=main` unless you've verified hardware support.

### General
- B-frame count (`bf`) above 3 on consumer NVENC silicon often shows diminishing returns. Workstation silicon tolerates higher values. Test for your specific GPU.
- `spatial_aq` and `temporal_aq` (adaptive quantization) are off by default. Turning both on typically improves perceived quality at marginal throughput cost — worth A/B testing.

---

## 7. Driver / SDK version sensitivity

NVENC behavior changes meaningfully between driver versions. When reproducing a reported NVENC issue, **driver version is a required input**, not incidental context.

- Minimum viable floor for recent research: driver 525.x+.
- Major behavior transitions historically track NVIDIA Video Codec SDK releases (11.x → 12.x → 13.x).
- Check NVIDIA Video Codec SDK release notes for specific behavior changes (https://developer.nvidia.com/video-codec-sdk).

Rule of thumb: if a forum post or Stack Overflow answer about NVENC behavior is more than ~2 years old and doesn't specify driver version, treat it as a starting hypothesis to verify, not settled knowledge.

---

## 8. Windows build considerations (gyan.dev)

gyan.dev publishes the most common prebuilt FFmpeg for Windows. The "full" build is the practical default for most use cases. Notable characteristics:

- **No libfdk_aac** (Fraunhofer AAC encoder, non-redistributable license). Use `-c:a aac` (FFmpeg native AAC) or build from source with fdk-aac linked in. At typical delivery bitrates (192 kbps+) the quality gap is narrow.
- All NVENC encoders present by default, including av1_nvenc.
- CUDA/cuvid hardware decoding present.
- Some non-free libraries missing — if you need libx264 10-bit, check build variant.

Alternative Windows builds:
- BtbN's auto-build (https://github.com/BtbN/FFmpeg-Builds) — includes fdk-aac GPL variant, recent master builds.
- Build from source via MSYS2 for full control (needed for libfdk_aac + NVENC + HDR metadata tooling combination).

---

## 9. Python integration — runtime GPU monitoring

For pipelines that monitor GPU state during encoding (throughput, utilization, thermal, session count), the standard binding is **nvidia-ml-py** (package imports as `pynvml`), which wraps NVML (NVIDIA Management Library).

Version note: in **nvidia-ml-py 13.x**, `pynvml.nvmlInit_v2()` was removed from the public API. `pynvml.nvmlInit()` now IS the v2 implementation. Tutorials and older code referencing `_v2` will raise `AttributeError`. Use bare `nvmlInit()`.

Useful NVML queries during encode monitoring:
```python
import pynvml
pynvml.nvmlInit()
handle = pynvml.nvmlDeviceGetHandleByIndex(0)
enc_util = pynvml.nvmlDeviceGetEncoderUtilization(handle)  # (percent, sampling_period_us)
dec_util = pynvml.nvmlDeviceGetDecoderUtilization(handle)
mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
```

NVML does **not** expose per-process NVENC session ownership cleanly on consumer drivers. For session-level debugging, cross-reference with `nvidia-smi dmon -s u`.

---

## 10. HDR workflows

NVENC can generate HDR bitstreams (HDR10, HLG) but color-space metadata handling is brittle. Missing tags silently produce non-HDR output on playback.

**Required tags for HDR10 (BT.2020 + PQ transfer):**
```
-color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc
-x265-params "hdr-opt=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:master-display=G(..)..:max-cll=..."
```
For NVENC HEVC, equivalent HDR metadata flags: `-profile:v main10 -pix_fmt p010le` plus the color flags above. Static HDR10 metadata (`master_display`, `max_cll`) must be preserved through the encode.

**For HLG (BT.2020 + ARIB STD-B67 transfer):**
```
-color_primaries bt2020 -color_trc arib-std-b67 -colorspace bt2020nc
```

`h264_nvenc` will silently produce non-HDR output from HDR sources without explicit color-tagging flags. There is no error. Validate output via `ffprobe -show_streams` on the encoded file.

**Alternative: NVEncC (rigaya)** — third-party wrapper that exposes NVENC directly, often cited as more robust for HDR workflows than raw FFmpeg+NVENC. Automatic HDR10/HLG metadata passthrough is more reliable. Repository: https://github.com/rigaya/NVEnc. Worth evaluating if HDR is a primary workload.

---

## 11. Command pattern reference

### Simple migration (CPU → GPU, H.264)
Before:
```
ffmpeg -i INPUT -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k OUTPUT.mp4
```
After:
```
ffmpeg -i INPUT -c:v h264_nvenc -preset p5 -rc vbr -cq 21 -c:a aac -b:a 192k OUTPUT.mp4
```

### HEVC with hardware decode + encode
```
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i INPUT \
  -c:v hevc_nvenc -preset p6 -rc vbr -cq 22 -b_ref_mode each \
  -c:a aac -b:a 192k OUTPUT.mp4
```

### 10-bit HEVC archival through hwaccel (requires hwdownload)
```
ffmpeg -hwaccel cuda -i INPUT \
  -vf hwdownload,format=nv12,format=p010le \
  -c:v hevc_nvenc -profile:v main10 -preset p7 -rc vbr -cq 20 \
  -pix_fmt p010le -c:a aac -b:a 192k OUTPUT.mkv
```

### AV1 encode (Ada+ only)
```
ffmpeg -i INPUT -c:v av1_nvenc -preset p6 -rc vbr -cq 28 \
  -c:a libopus -b:a 128k OUTPUT.mkv
```

---

## 12. Validation checklist post-encode

1. `ffprobe -show_streams OUTPUT` — verify codec_name, pix_fmt, color_space, color_transfer match intent.
2. Visual spot-check in a reference player (VLC is adequate; for HDR, a calibrated HDR display + player).
3. For quality claims, VMAF comparison against source (or a reference libx264/libx265 encode) via `libvmaf` filter.
4. For HDR, confirm the player reports the stream as HDR (not SDR-rendered).

---

## 13. Further research entry points

- **NVIDIA Video Codec SDK docs** — canonical for parameter semantics: https://developer.nvidia.com/video-codec-sdk
- **FFmpeg NVENC wiki** — https://trac.ffmpeg.org/wiki/HWAccelIntro
- **NVENC encoder param dump** — `ffmpeg -h encoder=hevc_nvenc` (local truth for your build)
- **NVIDIA developer forum** — driver-specific issue triage: https://forums.developer.nvidia.com
- **FFmpeg mailing list archives** — empirical parameter interaction reports
- **rigaya/NVEnc GitHub** — HDR-focused alternative, detailed param docs
- **jellyfin/jellyfin-ffmpeg** — production-tuned FFmpeg build with hardware-encode presets worth reading for pattern reference

---

## Notes for the next researcher

- Most NVENC "best practice" content on the web is pre-Ada (pre-2022) and skips AV1 entirely. Weight recent (2024+) sources accordingly.
- Official NVIDIA documentation tends to undersell pitfalls (silent-failure modes in §6). Community sources (FFmpeg mailing list, Doom9 forums, jellyfin maintainers) are the source of truth for empirical parameter-interaction issues.
- When a source cites NVENC behavior without driver version, treat the claim as time-bounded and verify.
