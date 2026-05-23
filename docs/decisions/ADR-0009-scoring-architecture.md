# ADR-0009: Local-only originality / quality scoring architecture

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** ADR-0001 (narrow pytest exceptions), ADR-0003 (narrow pytest extension), ADR-0008 (VMAF thresholds), Phase 3.1 persistent queue

## Context

Phase 3.2 adds a scoring system so users can measure how a render compares to its source: both on a "quality" axis (how close to the source) and an "originality" axis (how different from the source — relevant to the product's derivative-content use case). The design doc surveyed VMAF, SSIM, PSNR, and perceptual hashing.

Three constraints from Adam's approval message:

1. **Local-only.** No cloud rendering, no remote analysis service, no account/login, no remote model download at runtime, no external API. Same invariant as Phase 3.1.
2. **Additive and reversible.** Must not change `RenderWorker`, the ffmpeg encode command path, the Phase 3.1 queue, the GPU semaphore, or `output_collision` semantics. Disabling the feature returns the app to byte-equivalent behavior.
3. **Default-off auto-scoring.** VMAF on a 60s 1080p clip can cost 30–60s of single-thread CPU; auto-scoring a 50-task batch silently appends roughly 50 minutes of CPU. Opt-in only.

## Decision

### D1. Three exposed axes, no collapsed composite

`ScoreResult` exposes VMAF (mean + p5), SSIM (All), PSNR (average), and pHash (avg + max Hamming distance). The UI shows three columns (VMAF / pHash / SSIM); PSNR is computed alongside SSIM in a single ffmpeg pass and stored in the cache but not given its own column (the user can read it in the tooltip / future report view).

We deliberately do **not** collapse the four numbers into a single "originality score". Quality and originality are opposite axes for this product; collapsing them hides the trade-off the user is optimizing against.

### D2. dHash, not DCT pHash

The perceptual-hash runner uses **dHash** (difference hash): resize to 9×8 grayscale, emit 8 bits per row comparing adjacent pixel intensities, yielding a 64-bit hash. Hamming distance is the popcount of the XOR.

Rationale: dHash requires only Pillow (already pinned in `requirements.txt` since Phase 2c) and pure-Python comparison. DCT-based pHash would have pulled numpy or required a hand-rolled 32×32 DCT (~80 LOC of numeric code that needs its own correctness tests). dHash is well-studied, robust against re-encoding artifacts, and within ~1 bit of DCT pHash on standard benchmarks for our intended frame-pair use case. No numpy is added to the runtime surface.

### D3. Frame sampling, not full decode

`score_phash` extracts `n_frames` (default 20) equally-spaced single-frame JPEGs via `ffmpeg -ss <t> -i <video> -frames:v 1`. Pillow decodes each in memory; no temp files. The sample window deliberately trims the first/last 2% of clip duration so fade-in/fade-out black frames don't collapse the average distance to zero.

Cost on a 60s 1080p clip: roughly 1s per file (20 keyframe seeks × ~50ms each), so 2s total for the (reference, distorted) pair. This is the cheapest of the three axes.

### D4. SSIM + PSNR share a single ffmpeg pass

Both metrics fit in one filtergraph using `split` to fan the streams. Output parsing is regex on ffmpeg stderr (`SSIM ... All:0.989`, `PSNR ... average:51.20`) — no `stats_file=` temp file needed. This halves the cost of computing both metrics.

### D5. Capability probe at startup, not per render

`core.scoring.capabilities.detect(ffmpeg_path)` runs once in `VideoRendererTool.__init__`, parses `ffmpeg -filters`, and stores a `ScoringCapabilities` snapshot on the renderer. Mirrors the `gpu_detect._probe_ffmpeg_encoders` pattern. The render hot path is untouched — `start_render` never asks "can we score this?".

If the probe fails (binary missing, timeout, permission denied), `ScoringCapabilities.probe_error` is set and all ffmpeg-based axes report `False`. pHash remains available because it only needs Pillow + raw frame extraction (which every ffmpeg supports). The scoring UI degrades gracefully — "—" in the missing-axis column with a tooltip naming the cause.

### D6. ScoreWorker on its own thread pool, never blocking the render

`ScoreWorker` is a `QObject` moved to a dedicated `QThread`, separate from the render thread pool. The render pool size is unchanged. Scoring concurrency defaults to 1 (libvmaf is internally multi-core; running 2 in parallel mostly thrashes cache). Configurable 1–4 via Settings.

Trigger paths, ranked by foot-gun risk:

1. **Manual right-click** on any rendered row → "Score this render" / "Score selected" / "Score all rendered rows". Always available.
2. **Auto-after-render** when `scoring_auto_enabled=True` (default **False**). Spawned at the tail of `on_render_completed`.

The first trigger path needs no Settings opt-in; the second is opt-in only.

### D7. Local persistent cache mirrors Phase 3.1 queue store

`ScoreCache` (`core/scoring/score_store.py`) writes `scores.json` next to Phase 3.1's `queue.json` in the user's `user_data_dir`. Atomic write via the existing `core.atomic_write.save_json_atomic`. Schema-version reject + never-raises `load()` matches the queue store contract. The cache key is sha256(reference_path + 0x00 + distorted_path); the cached row stores both files' mtimes so an in-place re-render invalidates the score automatically.

No file lock. The cache is single-writer in practice (ScoreWorker pool + Qt main-thread reads, both serialised through a `threading.Lock` inside `ScoreCache`). Multi-instance is an edge case already handled by the Phase 3.1 queue store's `O_EXCL` lock on the more critical surface; an over-written score-cache row is recoverable by re-scoring.

### D8. ADR-0008 thresholds carry forward as UI colour bands

VMAF mean ≥ 96.0 and p5 ≥ 93.0 (ADR-0008 calibrated thresholds) become the green/yellow/red boundaries in the UI cell:
- green: mean ≥ 96 and p5 ≥ 93
- yellow: anywhere between
- red: mean < 90 or p5 < 85

Implementation note: cell colouring is deferred to a follow-up commit if the visual style needs Adam's review; the current commit renders cells uncoloured with a tooltip showing both values.

### D9. ADR-0003 narrow-pytest exception extension

All `tests/smoke/test_score_*.py` files claim ADR-0003 narrow-pytest exception status. They are:
- pure-Python (no Qt, no GPU)
- deterministic (no flaky network, no clocks)
- <2s total runtime
- not replaceable by a manual smoke log (they exercise schema validation, atomic-write semantics, and graceful-degradation paths that no human verification would catch reliably)

ADR-0001 manual-smoke remains the canonical verification for end-to-end render + UI behavior; this ADR extends the narrow-pytest list to cover the pure-IO scoring layer.

### D10. Out of scope (Phase 3.2)

Explicitly **not** in this phase, to preserve the additive-and-reversible contract:
- Cloud scoring API or remote upload of any video / hash / score.
- Login / account / per-user identity.
- Remote VMAF model file download — libvmaf's built-in default model only.
- Bulk N×N video comparison ("score these 100 videos against each other").
- Automatic preset recommendation derived from scores.
- Quality-gated re-render loop ("if VMAF < 96, re-encode at higher bitrate").
- ML-based content recognition beyond libvmaf and dHash.
- VMAF NEG mode (no-enhancement-gain variant).
- Cutter / merge / mixer integration — `auto_render.py` only this phase.

## Consequences

- One new package `core/scoring/` (7 files, ~1100 LOC) lands with no impact on existing modules at module-import time. RenderWorker, ffmpeg invocation, the Phase 3.1 queue store, and the GPU semaphore are unchanged.
- One additive ScoreWorker class lives next to `URLDownloadWorker` in `auto_render.py`.
- Three new columns on `tree_output` (positions 6/7/8) — strictly appended.
- One new Settings tab ("Scoring") with all controls defaulting to safe values.
- No new runtime dependency (Pillow was already pinned).
- No PyInstaller spec change required (`core/` is auto-included; libvmaf model file is internal to ffmpeg).

## Rollback

Phase 3.2 is fully reversible:
1. Disable the feature for any user by toggling Settings → Scoring → "Score every render automatically" off. Right-click menu remains available but is opt-in by interaction.
2. Removing the feature entirely is a single revert: delete `core/scoring/`, delete `tests/smoke/test_score_*.py`, remove the imports + helpers + columns + Settings tab from `auto_render.py` and `settings_dialog.py`. No data layout change; the orphan `scores.json` file in `user_data_dir` becomes inert and the next launch with the rollback build ignores it.
