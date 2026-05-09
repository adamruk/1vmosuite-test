# Benchmarks

Empirical performance and quality measurements backing changelog claims for 1vmo Suite.

## What belongs here

Any measurement a changelog entry depends on:

- Encoder throughput comparisons (hevc_nvenc vs libx264 vs AV1, etc.)
- Visual quality metrics (VMAF, PSNR, SSIM on a fixed test corpus)
- Memory, CPU, or GPU utilization during representative workloads
- Cold-start and processing-time measurements for the four apps

Rule: if a changelog entry uses the words "faster," "smaller," "better quality," or includes any number, the backing file lives here.

## What does NOT belong here

- Smoke tests and functional coverage — those go in `tests/`.
- Architectural reasoning — that goes in `docs/decisions/`.
- Ad-hoc developer curiosity runs that aren't cited in the changelog.

## Naming convention

```
YYYY-MM-DD-slug.md
```

- ISO date prefix so chronological sort == creation order.
- Slug describes the measurement, not the conclusion (`-nvenc-preset-vmaf-audit`, not `-nvenc-is-faster`).

Examples:
- `2026-04-18-nvenc-preset-vmaf-audit.md`
- `2026-04-25-ada-av1-throughput.md`

## Content expectations

Each benchmark file should capture enough for a skeptical reader six months later to verify or reproduce:

- Hardware: CPU, GPU, RAM, OS version, driver version
- Software: ffmpeg version, relevant library versions, commit hash of 1vmo Suite under test
- Input corpus: source files, resolution, duration, codec
- Methodology: exact commands, number of runs, how outliers were handled
- Raw numbers and the summary claim

## Referenced from CHANGELOG.md as

`[bench/2026-04-18-nvenc-preset-vmaf-audit.md]`
