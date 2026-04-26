# ADR-0004: Cross-platform expansion — Apple Silicon Mac added to platform targets

**Status:** Accepted (2026-04-23). Partially supersedes ADR-0002 (platform-scope clauses only).

**Date:** 2026-04-23

**Decision makers:** Adam (project lead)

**Context:**

ADR-0002 (Product trajectory: personal use, Windows only, commercial not currently planned) was committed on 2026-04-22 as part of Phase 2 governance. The platform-scope clause read: "Target platform: Windows only. macOS / Linux support is not planned. The bundled FFmpeg is Windows-only and the encoder pipeline assumes NVENC."

A part-time developer (Junaid) has joined the project. He has an Apple Silicon Mac (M4 Pro) and prior cross-platform video tooling experience. The user (Adam) also has access to an Apple Silicon Mac (M4 mini). Both team-internal users would benefit from native Mac support.

The decision to expand platform targets is being made at the same time as Junaid's onboarding. Mac compatibility work is sequenced AFTER Phase 2 stabilization ships, so this ADR authorizes future work without disturbing the current Phase 2 plan.

**Decision:**

1. Platform targets expand from Windows-only to Windows + Apple Silicon Mac (arm64).

2. Linux is explicitly skipped. No team member has Linux hardware to test on. Deferred until concrete demand emerges.

3. Intel Mac (x86_64) is explicitly skipped. Same reasoning as Linux — no testing hardware, all relevant team members are on Apple Silicon. Apple has been Apple-Silicon-only for new Mac sales since late 2023, so this covers all modern Macs.

4. Mac compatibility work begins AFTER Phase 2 stabilization ships. Phase 2 stabilization (60-hour plan: preset identity, schema, save-path fix, cancellation cleanup, 5 tests) proceeds on Windows as already planned. Mac port is a new phase (Phase 2.6) on top of stabilized foundation.

5. Junaid leads the Mac compatibility work. He has the Mac hardware and prior cross-platform video tooling experience. Adam reviews PRs on Windows for cross-platform regression checking.

6. Preset library will gain VideoToolbox-equivalent presets for hardware encoding parity. NVENC presets remain for Windows; new VideoToolbox presets target Mac. Encoder dispatch picks based on runtime platform/hardware detection (the gpu_caps capability detection landed early in Phase 2; full pipeline lands in Phase 2.5).

7. Junaid's first work is the URL input module (core/url_downloader.py), which is platform-agnostic by design — yt-dlp + Python work on both platforms with no Mac-specific code. This module ships independently of the Mac port and integrates into auto_render.py after Phase 2 stabilization ships.

**What ADR-0002 still constrains:**

ADR-0002's other clauses remain in force:
- Personal/team-internal use only — no commercial productization currently planned
- Solo (now solo + part-time dev) development model
- No SaaS, no user accounts, no billing
- No paid API dependencies for core 1vmo functionality (URL module is free; AI features deferred)

This ADR ONLY supersedes the platform-scope clause of ADR-0002.

**Consequences:**

- ADR-0002 receives a status header amendment noting partial supersession.
- A new phase (Phase 2.6: Mac compatibility) joins the roadmap, sequenced after Phase 2 stabilization and Phase 2.5 (Phase 1 features port).
- Bundled FFmpeg gains a macOS arm64 binary in addition to the Windows binary.
- Build pipeline gains a macOS variant (PyInstaller for Mac) in addition to Windows .exe.
- Encoder abstraction (currently NVENC-or-fallback) gains VideoToolbox awareness.
- The team's "all on Apple Silicon" assumption is documented; if a future user has an Intel Mac or Linux, this ADR can be reconsidered with concrete demand evidence.

**Out of scope for this ADR:**

- AI features (captions, preset picking, voiceover) — these stay in backlog, not authorized by this ADR.
- Commercial productization — ADR-0002's personal/team-internal scope still applies.
- iOS, Android, web — not under consideration.
- Linux — deferred without prejudice; revisit if hardware becomes available.

**References:**
- ADR-0002 (partially superseded by this ADR)
- PHASE_2_PORT_NOTES.md (Phase 2.5 work scope, separate from Phase 2.6 Mac port)
- ROADMAP.md (Phase 2.6 added as new phase)
