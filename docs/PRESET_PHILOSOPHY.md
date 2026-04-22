# Preset Philosophy

Design principles and authoring guidelines for 1vmo Suite presets. New presets added in Phase 2 onward should follow these; the existing 111-preset library can be audited against this rubric when the audit is picked up from backlog (2c-e Part B in `PHASE_2C_PLAN.md`).

Cross-references: `docs/ROADMAP.md` (phase status, observations), `docs/PHASE_2C_PLAN.md` (Phase 2 blockers + backlog), `docs/NVENC_PARAMETER_REFERENCE.md` (Windows-only NVENC parameters).

---

## Core principles

### 1. A preset expresses one intent

Every preset has a purpose describable in one sentence (*"export an Instagram story at 1080×1920 with aggressive color saturation"*). If you can't, the preset is likely a debug artifact or a kitchen-sink hybrid — split it or remove it.

**Anti-pattern:** names like "Custom 1", "Copy of Cycle 10s", or "Test". Cull aggressively.

### 2. Param lists are position-sensitive and whitespace-tokenized

FFmpeg parses positionally. The JSON schema stores `params: list[str]`. Two rules:

- **Do not merge separate tokens.** `-vcodec libx264` is two tokens.
- **Do not split atomic tokens.** `-filter_complex "[0:v]scale=1920:1080[v]"` is two tokens (flag + value); the value itself is one list element even though it contains spaces when shell-quoted.

Pydantic validation (Phase 2c-c-1) catches some cases; human review remains the safety net.

### 3. Observation V blocks HEVC and NVENC presets until fixed

The codec-append gotcha in `RenderWorker.process()` silently overrides `-vcodec libx265`, NVENC codecs, and `-c:a copy`. See ROADMAP.md Observation V. Scheduled fix: standalone commit during Phase 2.

**Authoring implication.** Do not ship new HEVC or NVENC presets until the fix lands. Use `tests/repro/observation-v-codec-append.py` to verify behavior change when that time comes.

### 4. Cross-platform authoring — one intent, three variants

The team splits 3 Windows / 2 Mac. Presets fall into three platform categories:

| Category | Codecs | Runs on |
|---|---|---|
| Cross-platform CPU | `libx264`, `libx265`, `libvpx-vp9` | All. **Default for new presets** unless hardware acceleration is specifically wanted. |
| Windows NVENC | `h264_nvenc`, `hevc_nvenc`, `av1_nvenc` | Windows with NVIDIA GPU. Mac shows "unavailable on this platform" info message (after 2c-c-6 ships). |
| Mac VideoToolbox | `h264_videotoolbox`, `hevc_videotoolbox` | Mac only. Hand-authoring allowed; most cycle families won't have these variants until 2c-d (backlog). |

**Rule.** When a user action ("render at best quality") can be served by multiple variants, author them as a family sharing a common approach. When `extends:` lands (backlog 2c-c-5), this becomes explicit via parent/child relationships; until then, families share conventions by hand-authored consistency.

### 5. `extends:` is backlog — currently flat presets only

The `extends:` schema field was planned for sub-phase 2c-c-5 and is currently backlog per ROADMAP. All presets authored during Phase 2 are flat (no inheritance). When 2c-c-5 is picked up later, factoring opportunities can be revisited.

---

## Taxonomy: 5 primary groups + sub-groups

This taxonomy is preserved. Renaming is not planned. If product direction changes materially, taxonomy revisit would be a future ADR decision.

**Primary groups.**

- **🕹️ 1vmo Ultimate** — zoom cycles, multi-layer cinematic effects, overlay + blurred-background composites. Highest filter-graph complexity. Highest kitchen-sink risk — audited first if 2c-e Part B is picked up.
- **🎮 1vmo Gaming** — gaming-optimized (high motion, HUD detail preservation, low latency).
- **🎬 1vmo Movie** — movie-style (gradient preservation, color grading compatibility).
- **🎵 1vmo Music** — audio-only or audio-dominant.
- **🎥 1vmo Social** — social-media formats (Instagram, TikTok, YouTube Shorts).

**Sub-groups.** 🎞️ Frame (flip), 🔖 Metadata & Text (drawtext, overlays), 💎 Quality (contrast, sharpening, grain), 🔍 Zoom (zoompan — simpler than Ultimate cycles), 🖼️ Image (frame extraction), 🌈 Color & Effect (B&W, saturation), Text (hardcoded defaults hoisted in 2c-b).

**Adding a new group** requires justification against kitchen-sink criteria below. Don't add a group for one preset.

---

## Kitchen-sink anti-pattern criteria

The 2c-e Part B audit flags presets matching any of these. For now (Phase 2), these criteria guide authoring of new presets only. Existing preset audit is backlog.

### Red flag 1 — multiple unrelated `-filter_complex` chains

Zoom cycle + overlay + drawtext + color grade in one chain is too much. Users wanting only zoom can't combine it with their own text or grading. Split into composable presets.

**Threshold:** more than 3 distinct unrelated filter operations. "Unrelated" = no common purpose. Scaling + padding is related (geometry). Scaling + drawtext is not.

### Red flag 2 — conflicting or redundant codec parameters

- `-preset slow` with `-crf 0` (lossless mode — preset tuning has no effect).
- `-b:v 5M` with `-crf 18` (bitrate/quality modes exclusive; last-wins wins silently).
- `-c:a aac` with `-c:a copy` (direct contradiction).

Assembly-without-validation smell.

### Red flag 3 — params contradicting stated intent

"High Quality Archive" with `-preset ultrafast`. "Fast Social Export" with `-preset veryslow`. Description and params must tell the same story.

### Red flag 4 — undeclared input assumptions

A preset assuming 16:9 input without declaring it produces stretched output on 9:16 sources.

**Rule.** Presets must (a) work on arbitrary input, or (b) clearly declare input assumptions in the `details` field.

### Red flag 5 — emoji/cosmetic-only variants

Two presets differing only in emoji or Vietnamese-vs-English description: cosmetic, not substantive. Consolidate.

---

## Authoring checklists

### Adding a preset

1. **Single intent** — describable in one sentence?
2. **Platform declared** — Windows NVENC, Mac VideoToolbox, cross-platform CPU? Stated in description?
3. **Observation V check** — if HEVC or NVENC, has fix shipped? If not, hold.
4. **Kitchen-sink check** — none of red flags 1-5?
5. **Name** — descriptive, not "Custom 1"?
6. **Description + details** — "what, when to use, what inputs"?
7. **Render test** — actually ran ffmpeg on a test clip; output matches intent? Attach sample render path for non-trivial presets.

Fails any item → revise or don't merge.

### Removing a shipped preset (from `encoder.builtin.json`)

User-facing behavior change. Rules:

1. **Deprecate first, remove later.** Add `deprecated: true` + `deprecation_note`. Keep loadable at least one release cycle.
2. **Document replacement** where possible (`deprecation_note` or `deprecated_replaced_by` field).
3. **User data preservation.** If users selected the removed preset in saved workflows, loader falls back to replacement or warns clearly.
4. **CHANGELOG entry** mandatory, with reason.

User presets in `encoder.user.json` are the user's own decision.

---

## Parametric generation (backlog — 2c-d)

Presets in a parametric family would be generated, not hand-authored. Currently backlog — sub-phase 2c-d deferred per ROADMAP.

When picked up, generator rules:

1. **Deterministic** — same inputs produce identical output. No timestamps, no random IDs.
2. **Idempotent in `encoder.builtin.json`** — re-running replaces generator's section without disturbing hand-authored presets.
3. **Tagged** — `generated: true` and `generator: "<name>-v1"` fields. Tools know not to hand-edit.
4. **Parameter-driven** — generator reads inputs from a single config file.

Hand-authored presets take precedence on ID collision. Generator fails loud on collision.

---

## Maintenance

This doc is stable until:
- Phase 2 completes and backlog items start getting picked up (may revise).
- An authoring pattern emerges that the kitchen-sink criteria don't cover.

Audit trail: `git log docs/PRESET_PHILOSOPHY.md`.