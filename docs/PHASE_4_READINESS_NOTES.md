# Phase 4 Readiness Notes

> **This file is NOT a Phase 4 design.** It records friction observed during Phase 3 implementation that Phase 4 should *consider*. No decisions are made here; no priorities are assigned. Adam picks what's worth pursuing.

## Observations

### O1. The encoder pipeline is closed
`core/preset_translator.py` handles a fixed set of NVENC codecs (h264_nvenc / hevc_nvenc / av1_nvenc) plus libx264 / libx265. Adding NVEncC, AMD VCN, Intel QSV, or VideoToolbox would either require editing this module in place or building a plugin layer that lets new codec families register themselves. Phase 4's "encoder plugin architecture" notes (parked in the Phase 3.6 design) are aimed here.

### O2. RenderWorker takes ~14 kwargs
`RenderWorker.__init__` has accumulated: video_path, encoder_names, thread_index, ffmpeg_path, output_directory, encoder_params_list, output_collision, gpu_error_action, gpu_enabled, gpu_codec, gpu_preset, gpu_max_quality_mode, gpu_semaphore. If a plugin architecture lands, this constructor wants to take a single `EncoderJob` dataclass instead of a flat kwargs sprawl.

### O3. UI tabs are at 6
General / Rendering / Advanced / GPU Pipeline / Scoring / Optimization (deferred). A 7th Orchestration tab was designed in Phase 3.4 but the implementation pass didn't add it (the toolbar buttons cover the common path; the Settings surface for max-retries / sleep prevention / scheduler policy is a follow-up). At 7+ tabs the Settings dialog becomes a UX problem.

### O4. Auto-retry policy is intentionally inert this milestone
Phase 3.4 ships the `RetryPolicy` + `decide_retry` machinery but auto_render does not yet call it on `on_render_error`. The wiring is small (10-15 LOC) but was kept out of Phase 3.4 to preserve "additive and reversible" — the retry layer can land in a Phase 3.4.1 follow-up once Adam confirms the allow-list of retry-eligible Kinds.

### O5. Encoder intelligence module ships without UI gate
Phase 3.5 ships the `classify_preset` + `compatibility_check` + `plan_fallback` functions but the Start-time pre-flight check (UI flow B in the Phase 3.5 design) is not yet a code path. The Phase 3.3 RecommendationDialog could call these today; a focused follow-up patch could wire the pre-flight modal that catches "av1_nvenc on Ampere" before Start hits ffmpeg.

### O6. Phase 3.6 updater hardening is documented, not wired
SHA256 verify + `_pending/` extract + backup-before-swap + queue-running guard are all designed in ADR-0013 D5. They are NOT yet in `updater.py`. Wiring them requires touching the updater hot path, which is a Phase 2d production-hardened surface — a follow-up patch should run the existing manual smoke matrix before + after.

### O7. PyInstaller spec drift
`1vmo-suite.spec` has not been edited to embed VERSION.txt via `datas=`. Currently `build_windows.py` copies VERSION.txt into the bundle *after* PyInstaller runs. In-spec inclusion is cleaner and survives custom spec extensions.

### O8. macOS spec doesn't exist yet
`1vmo-suite-macos.spec` is referenced by `build_macos.py` but the file hasn't been authored. The Windows spec doesn't have `BUNDLE()` blocks; cross-platform shipping needs the sibling spec.

### O9. The handoff zip is hand-curated
Phase 3.7 produces a zip layout (`docs/PHASE_3_HANDOFF.md`) but assembling it is manual. A `tools/build/assemble_handoff.py` would be useful but is out of scope for verification-only Phase 3.7.

### O10. ADR numbering is approaching collision
ADR-0001 through ADR-0014 are in use. New ADRs append cleanly, but a future "Phase 4 plugin architecture" might want to supersede ADR-0007 (GPU pipeline) and the supersession chain across 0007 / 0008 / 0012 will need careful drafting.

## What Phase 4 should NOT inherit as assumptions

- That "encoder plugin architecture" is the next-most-important feature. It might be; Adam decides.
- That the deferred items in O4, O5, O6 are urgent. Each is small and can land independently in a 3.x patch.
- That we need a CI runner. Phase 3.6 deliberately kept builds manual to preserve local-only. CI is a separate ADR if Adam wants it.
- That schema migrations are coming. Phase 3 ships a clean schema-reject contract. Migrations introduce a much larger surface to test; we've avoided them so far.

## What Phase 4 should inherit as guarantees

- RenderWorker contract is stable: signature, signals, process() body.
- user_data_dir layout is stable: every file is schema-versioned, the loader contracts are documented.
- ADR-0001 (manual UI/render smoke testing) and ADR-0003 (narrow pytest exceptions) remain binding.
- CLAUDE.md §12 PyInstaller rules remain binding.
- Local-only invariant remains binding.

## Closing

Phase 3 closed without any RenderWorker change, any forced encoder switch, any silent re-render, any cloud roundtrip, any account requirement, any destructive update, or any architecture rewrite. That contract was the whole point. Phase 4 should preserve it.
