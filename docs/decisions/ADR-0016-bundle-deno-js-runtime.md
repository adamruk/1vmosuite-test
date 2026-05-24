# ADR-0016: Bundle Deno (+ yt-dlp-ejs) as the JavaScript runtime for YouTube challenges

- **Status:** Accepted — implementation deferred to the packaging phase (see [B-044](../../BACKLOG.md))
- **Date:** 2026-05-24
- **Decision makers:** Adam (project lead)
- **Related:** ADR-0013 (release packaging — extends its build-side scope); ADR-0007 (GPU pipeline; the bundled-binary pattern this mirrors); C4 of Phase A url-dl hardening (resolver + PATH injection, merged `124ea1d`); B-044 (packaging task); B-045 (TikTok/curl-cffi — separate, not covered here)

---

## Context

Modern yt-dlp requires an external JavaScript runtime to solve the JS-based
"n-sig" / PO-token challenges that some extractors — most importantly YouTube —
now enforce. Without a runtime present, those downloads silently degrade
(throttled / format-limited) or fail outright. The challenge-solving scripts
themselves ship as the `yt_dlp_ejs` package, pulled in by the `yt-dlp[default]`
extra that Phase A pinned (`yt-dlp[default]>=2026.03.17`, C7).

Phase A's C4 added `_resolve_bundled_js_runtime()` to `core/url_downloader.py`:
it looks for a `deno`/`deno.exe` under `sys._MEIPASS` (frozen) then the repo
root (source), and prepends the directory to `PATH` at import so yt-dlp's
`shutil.which` discovers it. This mirrors the existing `_resolve_bundled_ffmpeg_dir`
pattern.

That resolves runtime discovery, but not runtime *availability* in a shipped
build. In **source mode** the developer/teammate installs Deno once
(`winget install denoland.deno`) and it lands on `PATH`. In a **frozen `.exe`**
there is no system Deno to find, and PyInstaller — which analyzes Python imports
— can omit the non-`.py` JS assets inside `yt_dlp_ejs`. So the `.exe` must ship
both the runtime and the challenge scripts itself, or YouTube breaks for end
users despite the code being correct. This ADR records how.

## Decision

For the frozen `.exe`, **bundle Deno as the JS runtime**, fetched at build time
(pinned, not committed) and staged exactly like the existing ffmpeg binary, and
**force-collect the `yt_dlp_ejs` assets** into the bundle.

Concretely:

1. A build-time fetch script downloads a **pinned** Deno for Windows (the full
   `deno`, **not** `denort`) into the bundled-tools directory, mirroring how
   ffmpeg is staged. The binary is `.gitignore`d, never committed.
2. The PyInstaller `.spec` adds `deno.exe` to `binaries=` at the **same
   `sys._MEIPASS` destination as ffmpeg**, so the existing C4 resolver finds it
   with no code change.
3. The `.spec` calls `collect_all('yt_dlp_ejs')` (confirm the exact package
   name at implementation time) so the JS challenge scripts are bundled
   (PyInstaller would otherwise drop them).
4. Verification is a **frozen-build YouTube extraction** — the bundled-`_MEIPASS`
   path cannot be proven any other way; source-mode tests do not exercise it.

## Alternatives considered

- **Require users to install Deno themselves.** Rejected: defeats the purpose of
  shipping a single double-clickable `.exe`; non-technical users won't, and
  YouTube would silently fail for them.
- **Node.js as the runtime.** yt-dlp-ejs supports several runtimes, but Node
  means an `npm`/`node_modules` footprint and a multi-file install that is
  awkward to freeze. Deno is a single self-contained binary — far simpler to
  bundle and version-pin.
- **Bun.** Also a single binary. Deno was chosen as an explicitly supported
  yt-dlp-ejs runtime with solid Windows support; either could work, and this can
  be revisited if Deno bundling proves problematic.
- **QuickJS or another embedded engine.** Not an officially supported yt-dlp-ejs
  runtime path; high risk of breakage as challenges evolve.
- **`denort` (Deno runtime-only) instead of full `deno`.** Smaller, but it lacks
  capabilities the ejs scripts rely on; the full `deno` binary is required.
- **Commit the Deno binary to git.** Rejected: the binary is large (roughly a
  ~40 MB download, ~100 MB-class on disk); committing it bloats history
  permanently. Fetch-at-build keeps the repo lean and the version explicit,
  matching the ffmpeg approach.
- **Pin "latest" rather than a fixed version.** Rejected: non-reproducible
  builds, and yt-dlp enforces a minimum JS-runtime version — a too-old Deno is
  rejected as unsupported. Pin a current 2.x and bump deliberately.

## Consequences

**Positive**
- YouTube extraction works in the shipped `.exe` with no user setup.
- Single self-contained runtime; no `node_modules`/multi-file install to freeze.
- Reproducible builds via a fixed Deno pin.
- No code change needed when bundling — the C4 resolver already checks `_MEIPASS`.

**Costs / negative**
- The `.exe` grows substantially (Deno adds a ~100 MB-class binary to the bundle).
- The build pipeline gains a network-dependent fetch step before PyInstaller.
- The Deno pin must be bumped periodically as yt-dlp raises its minimum runtime
  version; a stale pin will be rejected and break YouTube.
- The `collect_all('yt_dlp_ejs')` step is easy to forget and produces a failure
  that only shows at runtime in the frozen build (YouTube fails despite Deno
  being present) — hence the mandatory frozen-build extraction check.

**Maintenance triggers**
- When yt-dlp raises its minimum JS-runtime version → bump the Deno pin and
  re-verify a frozen-build YouTube extraction.
- Each packaging cycle → confirm `deno.exe` and the bundled `yt_dlp_ejs` `.js`
  assets are present in `dist/` and that a real YouTube URL extracts from the `.exe`.

## Notes

- This ADR covers the **decision and rationale**; the executable checklist lives
  in **B-044**. Source-mode use needs none of this — just Deno on `PATH`.
- TikTok's separate failure mode (yt-dlp impersonation needing `curl-cffi`) is
  unrelated and tracked under **B-045**.