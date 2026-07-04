"""Smoke gate: main-window minimum-size ratchet (v3.9 UI hardening).

Instantiates VideoRendererTool offscreen (never calls app.exec, mirroring
the 2026-06-10 UI recon harness) and asserts the window's minimumSizeHint
stays under a ceiling. The ceiling RATCHETS DOWN as UI batches land:

    Batch UI-1 (QSS scoping + toolbar FlowLayout)   -> 1600 x 820
    Batch UI-2 (slot-row FlowLayout + combo policy) -> 1400 x 820
    Batch UI-3 (splitters + frame floors lowered)   -> 1280 x 800   (current: interim 1100 x 720)
    Batch UI-4 (final polish)                       -> 1100 x 700

Tighten CEILING_W / CEILING_H in the same commit as each batch.

Notes:
- QT_QPA_PLATFORM must be set BEFORE PySide6 is imported.
- Skips when the bundled ffmpeg is absent (CI runner): VideoRendererTool's
  _check_dependencies raises a modal + sys.exit without it, which would
  hang an offscreen run. The gate is therefore effective on dev machines
  and in the local recon flow; CI skips gracefully (matches the existing
  tests/smoke convention).
- Instantiation rewrites "assets/Version AutoRender.json" (B-054). If your
  gate requires a clean tree afterwards:  git restore "assets/Version AutoRender.json"
- The window is NOT close()d: closeEvent would save_config() into the
  user-data dir as a side effect. We only need the polished size hint.

Target location in the repo: tests/smoke/test_ui_minsize.py
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

_FFMPEG = REPO_ROOT / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")

pytestmark = pytest.mark.skipif(
    not _FFMPEG.exists(),
    reason="bundled ffmpeg absent — VideoRendererTool exits at dependency check",
)

# Ratchet values — tighten with each landed UI batch (see module docstring).
CEILING_W = 1100
CEILING_H = 720


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_main_window_minimum_size_ratchet(qapp):
    import auto_render

    window = auto_render.VideoRendererTool()
    # ensurePolished forces the QSS polish pass so stylesheet-derived
    # min/max constraints are reflected in the hint. No event loop runs,
    # so the QTimer.singleShot(0) resume prompt never fires (same trick
    # the recon used).
    window.ensurePolished()
    hint = window.minimumSizeHint()

    # Always print the measured value so recon/VERIFY records have the
    # actual number, not just pass/fail.
    print(
        f"minimumSizeHint = {hint.width()} x {hint.height()} "
        f"(ceiling {CEILING_W} x {CEILING_H})"
    )

    assert hint.width() <= CEILING_W, (
        f"window minimum width regressed: {hint.width()} > {CEILING_W}"
    )
    assert hint.height() <= CEILING_H, (
        f"window minimum height regressed: {hint.height()} > {CEILING_H}"
    )
