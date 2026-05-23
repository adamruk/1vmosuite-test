# ADR-0015: Single-knob NVENC codec routing in translate_to_nvenc (B-015)

**Status:** Accepted

**Date:** 2026-05-24

**Decision makers:** Adam (project lead)

**Supersedes:** none

**Amends:** none (clarifies the scope of ADR-0007 D4; does not change any ADR-0007 decision)

## Context

`core/preset_translator.py::translate_to_nvenc` converts a preset's CPU encoder
params to NVENC equivalents. When a preset specifies a CPU video codec
(`-c:v libx264` / `-c:v libx265`), the translator must choose which NVENC encoder
to emit. Two models are possible:

- **Per-preset map:** libx264 → h264_nvenc, libx265 → hevc_nvenc (the NVENC codec
  follows the preset's CPU-codec intent).
- **Single-knob:** the emitted NVENC codec is the user's `gpu_codec` setting (the
  Settings dropdown from ADR-0007 D4), regardless of the preset's CPU codec.

The shipped implementation has always used **single-knob** routing: it computed a
per-preset `mapped` value but then ignored it for recognized CPU codecs, emitting
the `codec` kwarg (the `gpu_codec` setting) instead.

B-015 surfaced this as a contradiction with "ADR-0007 D4 (`libx265 → hevc_nvenc`)".
On review, **ADR-0007 D4 is the codec-_dropdown_ decision** (which codecs appear in
Settings — H.264 default, HEVC available, AV1 experimental); it contains **no**
per-preset routing rule. The `_CODEC_MAP` "per ADR-0007 D4" comment was therefore a
mis-citation, and the `mapped` variable was dead for the recognized-codec path,
making the code read as if per-preset routing were intended when it was not.

## Decision

Codify single-knob routing as the intended, supported behavior:

1. When a preset's `-c:v` / `-vcodec` names a CPU codec in `_CODEC_MAP`
   (libx264/libx265), the emitted NVENC codec is the user's `gpu_codec` setting
   (the `codec` kwarg). The preset's specific CPU codec does **not** select the
   NVENC codec.
2. Codecs not in `_CODEC_MAP` (already-NVENC encoders; av1 sources such as
   libsvtav1/libaom-av1; anything unrecognized) pass through unchanged.
3. `_CODEC_MAP` is retained, but only its **keys** are normative (the set of CPU
   codecs eligible for translation). Its values are documentation only.
4. The misleading unused `mapped` variable is removed.

This is a documentation/clarity change, **not a behavior change** — output is
byte-identical to the prior shipped behavior, verified by characterization tests in
`tests/smoke/test_preset_translator_routing.py`.

## Consequences

**Positive:**

- One control governs GPU codec selection (the `gpu_codec` dropdown), matching
  ADR-0007 D4's single-default design and ADR-0007 D8's persisted `gpu_codec` key.
- The code no longer implies a per-preset routing model it does not implement.
- The D4 mis-citation is corrected.

**Negative / trade-off:**

- A libx265 ("HEVC-intent") preset rendered on the default `gpu_codec=h264_nvenc`
  produces H.264, not HEVC. Users who want HEVC output set `gpu_codec=hevc_nvenc`
  in Settings. This is the documented, intended behavior (the dropdown is the single
  source of GPU-codec truth), but it can surprise users who expect a preset's CPU
  codec to carry across to the GPU path.

**Neutral:**

- If per-preset routing is ever desired, it would require a new ADR superseding this
  one, plus wiring a per-preset map back into the translator.

## Alternatives considered

**Honor `_CODEC_MAP` per-preset (libx265 → hevc_nvenc).** Rejected for this pass: it
is a behavior change to NVENC routing (high-risk per CLAUDE.md §13), would override
the user's single `gpu_codec` choice on a per-preset basis, and contradicts D4's
single-default dropdown model. Deferred as a possible future ADR if user demand
surfaces.

## References

- `core/preset_translator.py` — `translate_to_nvenc`, `_CODEC_MAP`
- `tests/smoke/test_preset_translator_routing.py` — characterization coverage
- ADR-0007 D4 — codec dropdown (the decision B-015 was mis-attributed to)
- ADR-0007 D8 — `gpu_codec` settings persistence
- BACKLOG.md — B-015

## Related

- ADR-0007 (GPU/NVENC pipeline architecture)
