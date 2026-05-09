# Phase 1 — Stop Conditions

## Scope

This document defines the conditions under which Phase 1 work (NVENC detection → preset porting → benchmarking) should halt for reassessment rather than continue forward. Scoped to Phase 1 only; later phases get their own stop-condition documents as needed.

This is a lightweight, single-developer adaptation of pivot/persevere/kill decision logic from Lean Startup — not Stage-Gate or other enterprise frameworks. The value is cheap insurance against the sunk-cost fallacy, not process theater.

Related: `FFMPEG_CPU_TO_NVENC_REFERENCE.md` §1/§6/§7.

## Time budget

**3 working days of active effort** on Phase 1, counted from the day preset porting begins (detection scaffolding already done).

If day 3 ends and Phase 1 is not substantively complete, stop and reassess scope before continuing. Do not push through past the budget without a recorded reason captured as an ADR under `docs/decisions/`.

## Hard stops — pause work, verify, escalate for Adam's decision

**H-1. NVENC initialization failure.**
`h264_nvenc` cannot encode a known-good 10-second 1080p sample without error on the reference machine, even after updating to current driver (595.97 or later).

**H-2. Silent broken-output pattern.**
Any §6 pitfall from the NVENC reference doc (weighted_pred + bf on H.264 producing broken output, b_ref_mode=each emitting non-compliant streams, 4:4:4 silent acceptance, 10-bit hwdownload memory errors) manifests in ported presets AND cannot be reliably detected at preset-load time via ffprobe or a validation sniff test.

**H-3. Throughput floor.**
Sustained wall-clock speedup <3× vs libx264 on the canonical test clip, measured across ≥3 runs on ≥2 different source clips at matched output quality. Below this, NVENC's core value proposition has failed for this workload.

## Soft stops — log in benchmark file, continue work, review at end of phase

**S-1.** VMAF drop >4 points at matched file size on more than 2 of the top 10 ported presets.

**S-2.** Thermal throttling reduces batch throughput by >40% over a 30-minute sustained run on the Legion 9.

**S-3.** AV1 encoding specifically fails or underperforms — treat as Conditional Go territory (ship H.264 + HEVC, defer AV1), not a hard stop.

## Verification & permission protocol

This section is binding on Claude Code and any other automated helper working on Phase 1.

When an automated helper observes something that *looks like* a hard-stop trigger (H-1, H-2, or H-3), it must NOT take autonomous action.

### Prohibited autonomous actions

- Rolling back code, commits, or configuration
- Disabling features, presets, or capability flags
- Adding fallback paths, try/except swallowing, or defensive error handling that was not explicitly requested
- Skipping or excluding presets that fail benchmarks
- Changing phase scope or deliverables
- Opening issues, filing tickets, or modifying project documents outside the scope of the current task
- Declaring Phase 1 halted, killed, pivoted, or held
- Writing ADRs, tech-debt entries, or changelog entries that encode the "halt" as a decision

### Required sequence when a hard stop appears triggered

1. **Verify the signal.** Re-run the failing measurement at least 2 more times under the same conditions. Classify the result as *sustained* (fails consistently) or *intermittent* (mixed results). These have different implications.

2. **Rule out operator/environmental causes.** Before concluding NVENC is broken, check: wrong ffmpeg path, wrong input file, GPU in use by another process, thermal state, driver version mismatch, corrupted test clip, wrong measurement methodology, wrong encoder params for the preset.

3. **Produce a structured report** containing exactly:
   - Which stop condition appears triggered (H-1, H-2, or H-3)
   - Raw evidence: exact commands run, full stdout/stderr captured, verbatim
   - Verification steps taken and their results (the 2+ re-runs)
   - Environmental/operator checks performed and what each ruled out
   - Sustained vs intermittent classification
   - Possible interpretations, enumerated — no recommendation
   - Explicit closing line: `AWAITING ADAM'S DECISION — NO FURTHER ACTION TAKEN`

4. **Wait for explicit direction from Adam.** Resume work only after Adam responds with one of:
   - Continue (false alarm, proceed as before)
   - Fix and retry (Adam specifies the fix)
   - Pivot (Adam specifies the scope change — e.g., "drop AV1, ship H.264 only")
   - Halt Phase 1 pending further investigation

### Soft-stop handling

Soft stops (S-1, S-2, S-3) do not trigger this protocol. Log them to the benchmark file and continue working. Review at the Phase 1 close-out.

## Sunk-cost awareness

At any Phase 1 stop-condition trigger, the honest question is: am I continuing (or halting) because the evidence supports it, or because of time already invested? Effort already spent is not a reason to persevere through clear failure signals, and it is not a reason to kill through recoverable setbacks. Evidence drives the call.

## Decision authority

Adam. Named explicitly to avoid consensus ambiguity. Automated helpers inform the decision; they do not make it.

## Amendments

This document can be amended during Phase 1 if experience shows criteria are wrong (too loose, too tight, or missing conditions). Amendments are recorded as new ADRs under `docs/decisions/` that reference this file, not quiet edits.
