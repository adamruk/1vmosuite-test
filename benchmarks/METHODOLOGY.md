# Benchmark Methodology — Phase 1

## Purpose

This document defines how to run reproducible benchmarks for the 1vmo Suite NVENC migration (Phase 1). It exists because raw numbers from `bench.py` are only meaningful if the conditions under which they were measured are explicit and consistent. This doc encodes those conditions.

Related: `bench.py`, `benchmarks/README_BENCH_TOOL.md`, `docs/PHASE_1_STOP_CONDITIONS.md`, `FFMPEG_CPU_TO_NVENC_REFERENCE.md`.

## What gets measured

Three things, per (preset × clip × engine) combination:

1. **Wall-clock time** — how long the encode took, start to finish
2. **Output size** — bytes of the encoded file
3. **Quality** (full mode only) — VMAF mean and 5th percentile

The 5th percentile matters more than the mean for quality. A mean VMAF of 95 can hide a long tail of bad frames that viewers actually notice. We report both, but the 5th percentile is the honest metric.

## Test clip requirements

Phase 1 baseline benchmarks run on **3 canonical test clips**, picked once and reused for every measurement so results are comparable.

Required diversity across the 3 clips:

- **Clip A — high motion**: representative of intense gameplay or fast camera movement. This is the encoder stress case.
- **Clip B — mixed**: typical content with both motion and static scenes. Most representative of average workload.
- **Clip C — low motion / UI-heavy**: lobby screens, menus, talking-head style content, or anything with mostly static frames. Encoders look great on this kind of content; including it shows the upper bound.

Each clip should be **30 to 120 seconds** long. Shorter than 30s and per-encode overhead distorts measurements. Longer than 120s and benchmark cycles become too slow to iterate.

Test clips live **outside the repo** (they may be large, and they may be private gameplay footage). The measurement scripts and result files reference clips by absolute path. Document the canonical paths in this section once chosen, e.g.:

```
Clip A: C:\path\to\clip-a-high-motion.mp4
Clip B: C:\path\to\clip-b-mixed.mp4
Clip C: C:\path\to\clip-c-low-motion.mp4
```

(Adam: fill in the actual paths above when you've decided on the 3 clips.)

## The cold vs sustained distinction

Laptop NVENC chips throttle under sustained load. The same preset on the same clip can produce noticeably different throughput depending on whether the GPU was just woken up or has been encoding for 20 minutes. Phase 1 needs both numbers because they answer different questions:

- **Cold throughput** — what speedup is *possible* in best-case conditions. Useful for marketing claims and feature design.
- **Sustained throughput** — what speedup users will *actually get* during real batch jobs. Useful for honesty.

Stop-condition H-3 (the 3× speedup floor) applies to **sustained** throughput, not cold. A preset that hits 8× cold but 1.5× sustained fails the floor.

### Cold-state protocol

Before each cold-state measurement:

1. GPU has been idle for at least 5 minutes. No encoding, no gaming, no GPU compute. Verify with Task Manager → Performance → GPU (utilization should be near 0%).
2. Laptop has been on AC power (not battery) for at least 5 minutes. Battery operation triggers different power limits.
3. Laptop is in its normal physical position (not lifted off the desk for extra airflow, not in a special cooler).
4. Ambient temperature is consistent with normal use — record the room temperature in the result notes if the room is unusually hot or cold.

After these conditions are met, run the benchmark with `--runs 1`. The first encode is the cold-state measurement. Save the result, then wait at least 5 minutes before the next cold-state run.

### Sustained-state protocol

To measure sustained throughput, the GPU needs to be in its long-duration thermal equilibrium. Use this protocol:

1. Pick the preset to be measured.
2. Run a 20-minute warmup batch using the same preset and any clip — Clip B is fine. This establishes thermal equilibrium. The warmup output is discarded.
3. Without pause, immediately run the sustained-state measurement on the actual test clip with `--runs 3`. Use the average of the 3 runs as the sustained number.
4. After the sustained measurement, the GPU is "hot" — wait at least 10 minutes before any other measurement, or you'll contaminate the next benchmark.

Sustained measurements are slow (warmup + 3 runs). Budget ~45 minutes per (preset × clip × engine) combination. The full top-10-preset baseline sustained matrix is roughly a half day of unattended Legion time.

### Quick mode for iteration

While porting and tuning presets, full sustained measurements every cycle is overkill. Use this faster loop:

1. Run `bench.py --mode quick --runs 1` cold for fast iteration (~10 sec per cycle).
2. Validate the preset works, output looks right, no silent corruption.
3. Only when ready to commit a preset's settings, run the full cold + sustained matrix on it.

## Standard benchmark invocations

For all examples below, replace `<clip>` with the absolute path to one of the test clips, and replace the preset args with whatever encoder configuration is being measured.

### Quick CPU baseline (iteration)

```
python bench.py --input "<clip>" --mode quick --label "libx264_medium_crf20_quick" --preset-args "-c:v libx264 -preset medium -crf 20 -c:a copy"
```

### Full CPU baseline (commit-ready)

```
python bench.py --input "<clip>" --mode full --runs 3 --label "libx264_medium_crf20_full" --preset-args "-c:v libx264 -preset medium -crf 20 -c:a copy"
```

### Quick GPU comparison (iteration)

```
python bench.py --input "<clip>" --mode quick --label "h264_nvenc_p5_cq21_quick" --preset-args "-c:v h264_nvenc -preset p5 -rc vbr -cq 21 -c:a copy"
```

### Full GPU sustained measurement (after 20-min warmup)

```
python bench.py --input "<clip>" --mode full --runs 3 --label "h264_nvenc_p5_cq21_sustained" --preset-args "-c:v h264_nvenc -preset p5 -rc vbr -cq 21 -c:a copy"
```

## Result organization

Result JSON files land in `bench_results/` by default. For Phase 1, manually move them into `benchmarks/` as part of the audit trail when they back a changelog claim.

Naming convention for files in `benchmarks/`:

```
YYYY-MM-DD-<scope>-<engine>-<state>.md
```

Where:
- `scope` describes what was measured (e.g., `top10-libx264-baseline`, `preset-3-nvenc-port`)
- `engine` is `cpu` or `nvenc`
- `state` is `cold`, `sustained`, or `mixed` (when both are in one report)

Example: `benchmarks/2026-04-19-top10-libx264-baseline-cold.md`

Each promoted benchmark file is a markdown summary of the run — input clips used, exact commands, raw JSON files referenced, and a small results table. The raw JSON stays in `bench_results/` as evidence; the markdown is the human-readable digest.

## What good benchmark hygiene looks like

A measurement is trustworthy when all of the following are documented in the result:

- The exact ffmpeg command (the `ffmpeg_command` field of bench.py's JSON output)
- The driver version at time of measurement (record manually — bench.py captures GPU name but driver version may need to be added by hand)
- Whether the run was cold or sustained
- AC power state (always record)
- Approximate ambient temperature if abnormal
- Number of runs and stddev (for runs > 1)

A measurement is worthless when any of these are unclear.

## Common pitfalls

- **Battery measurements.** The Legion 9 cuts CPU and GPU power on battery. Benchmarks on battery are not comparable to benchmarks on AC. Always use AC.
- **Background load.** A browser playing a video, a Discord call, an OBS stream — all consume CPU/GPU and contaminate measurements. Close everything except essentials before benchmarking.
- **Mixing cold and sustained in one batch.** If you run 5 cold-state benchmarks in a row without pauses, only the first one is truly cold. Subsequent ones are at varying thermal states and are neither cold nor sustained.
- **Trusting a single quick-mode run.** Quick mode skips VMAF — useful for "did the encode crash?" but not for quality claims. Always confirm with full mode before committing a preset.
- **Forgetting the warmup.** Sustained measurements without a 20-minute warmup are just slightly-warmer cold measurements. They don't capture true throttled-state performance.

## When this methodology updates

This doc is amendable as Phase 1 progresses. If we discover the cold/sustained protocol misses something — say, the laptop has a third thermal regime we didn't account for — amend this doc and reference the discovery in `docs/decisions/` as an ADR.

Do not silently change methodology mid-Phase-1. Numbers measured under one methodology cannot be directly compared to numbers measured under another.
