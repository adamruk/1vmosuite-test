# bench.py — benchmark tool

Standalone tool for measuring ffmpeg commands: wall-clock time, output size, and (in full mode) VMAF quality. Used to produce the numbers that drive Phase 1 NVENC migration decisions.

Not integrated into the GUI apps — invoked manually.

## Invocation

```
python bench.py --input <video> --preset-args "<ffmpeg arg string>" --mode {quick|full}
                [--output-dir <dir>] [--label <name>] [--runs <N>]
```

- `--input` — path to the input video.
- `--preset-args` — ffmpeg argument string between input and output (encoder/filter portion only). The tool prepends `-progress pipe:1 -i <input>` and appends the output filename.
- `--mode` — `quick` (wall-clock + size, ~10 s overhead) or `full` (adds VMAF, ~60 s overhead). Default: `quick`.
- `--output-dir` — where encoded outputs and JSON results land. Default: `./bench_results/`.
- `--label` — human-readable name used in output filenames and JSON. Default: sanitized from `--preset-args`.
- `--runs` — run the benchmark N times and report mean + stddev. Default: `1`.

`python bench.py --help` prints the above inline.

## Modes: when to use which

| Mode  | Measures                                        | Overhead       | Use when                                                                 |
| ----- | ----------------------------------------------- | -------------- | ------------------------------------------------------------------------ |
| quick | wall-clock, output size                         | ~10 s / run    | Exploring speed tradeoffs, sweeping many preset variants, spot checks    |
| full  | quick + VMAF mean, 5th percentile, min, max     | ~60 s / run    | Producing the numbers that back a changelog claim or feed an ADR         |

Rule of thumb: use `quick` while iterating on preset parameters, `full` once you've picked candidates worth measuring properly.

## Worked example: compare CPU vs GPU for the same target quality

Baseline libx264 at CRF 20:

```
python bench.py --input clips/gameplay-1080p.mp4 \
    --preset-args "-c:v libx264 -preset medium -crf 20 -c:a copy" \
    --mode full --runs 3 --label libx264_medium_crf20
```

NVENC target roughly the same file size (tune `-cq` until output size matches):

```
python bench.py --input clips/gameplay-1080p.mp4 \
    --preset-args "-c:v h264_nvenc -preset p5 -rc vbr -cq 23 -c:a copy" \
    --mode full --runs 3 --label nvenc_p5_cq23
```

Compare `bench_results/libx264_medium_crf20__result.json` against `bench_results/nvenc_p5_cq23__result.json`: `aggregate.wall_clock_mean` for speedup, `aggregate.output_bytes_mean` for size parity check, `aggregate.vmaf_mean_avg` and `vmaf_p5_avg` for quality. Target is comparable mean VMAF AND comparable p5 (worst-frame) — a big p5 drop means the GPU encode has a bad-frame pattern the mean hides.

## Interpreting the JSON output

`bench_results/<label>__result.json` has:

- `input.duration_seconds` — how long the source is. The throughput multiplier is `duration / wall_clock`.
- `runs[*].wall_clock_seconds` — encoder wall-clock per run.
- `runs[*].output_bytes` — output file size.
- `runs[*].vmaf_mean` / `vmaf_p5` / `vmaf_min` / `vmaf_max` — VMAF stats (full mode only). `vmaf_p5` = 5th-percentile per-frame VMAF, i.e. worst 5% of frames.
- `aggregate.*` — mean/stddev across runs. For single run, stddev is 0.
- `ffmpeg_command` — the reconstructed command with `<N>` in place of the run index.
- `ffmpeg_version` — first line of `ffmpeg -version`; differentiates bundled vs system builds.
- `system.gpu` — best-effort via `nvidia-smi`. Null if not available.
- `warning` — present only if VMAF measurement failed (but encode succeeded).

Failed runs set `encode_succeeded: false`, capture stderr in `error`, and the tool exits non-zero.

## Limitations

- **VMAF requires libvmaf in the ffmpeg build.** The bundled ffmpeg includes it; older or stripped builds may not. On failure, the tool reports the error in the JSON `warning` field and continues with quick-mode-equivalent results. It never substitutes PSNR or SSIM silently.
- **No PSNR or SSIM fallback** by design — VMAF is the target metric, mixed metrics are worse than missing metrics.
- **No thermal awareness.** Long `--runs N` sessions on a laptop may show throughput decay across runs. Run with thermal state in mind.
- **Outputs accumulate.** The tool never deletes encoded outputs; clear `bench_results/` manually when done.
- **Single-input only.** For multi-clip sweeps, script the invocation around the tool.
