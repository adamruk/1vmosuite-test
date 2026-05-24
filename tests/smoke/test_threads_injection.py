"""Smoke test: CPU path injects ``-threads 0``; NVENC path does not (C4, phase4).

Ported behavior — the CPU (libx264) encode path appends ``-threads 0`` so ffmpeg
auto-selects the worker thread count, unless the preset already pins ``-threads``.
The NVENC/gpu path never gets it (NVENC parallelism is governed by async_depth +
the GPU semaphore, not libavcodec threads).

``RenderWorker.process()`` is driven with a stubbed
``core_ffmpeg_runner.run_ffmpeg`` that captures the ffmpeg argv and fakes a
successful encode, so no real ffmpeg, GPU, or Qt event loop is exercised.
RenderWorker is a plain ``QObject`` (not a ``QWidget``), so it constructs without
a ``QApplication``.

ADR-0003 narrow exception (deterministic, no GPU/ffmpeg, single-purpose).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import auto_render  # noqa: E402


def _run_and_capture(monkeypatch, tmp_path, *, gpu_enabled, params):
    """Drive RenderWorker.process() once with run_ffmpeg stubbed; return the
    captured ffmpeg argv list for the single encode step."""
    captured: list[list[str]] = []

    def fake_run_ffmpeg(command, *args, **kwargs):
        captured.append(list(command))
        # command[-1] is the ffmpeg output target (after "-y"); create it so the
        # on-success os.replace can promote it to the canonical output path.
        Path(command[-1]).write_bytes(b"\x00")
        return 0

    monkeypatch.setattr(auto_render.core_ffmpeg_runner, "run_ffmpeg", fake_run_ffmpeg)

    src = tmp_path / "in.mp4"
    src.write_bytes(b"\x00")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    worker = auto_render.RenderWorker(
        video_path=str(src),
        encoder_names=["Test|enc"],
        thread_index=0,
        ffmpeg_path="ffmpeg",
        output_dir=str(out_dir),
        encoder_params_list=[list(params)],
        output_collision="overwrite",
        gpu_enabled=gpu_enabled,
        gpu_codec="h264_nvenc",
    )
    worker.process()
    assert captured, "run_ffmpeg was never called"
    return captured[0]


def _has_threads_zero(argv: list[str]) -> bool:
    return any(
        argv[i] == "-threads" and i + 1 < len(argv) and argv[i + 1] == "0"
        for i in range(len(argv))
    )


def test_cpu_path_injects_threads_zero_when_unpinned(monkeypatch, tmp_path):
    """gpu_enabled=False, preset without -threads -> libx264 + `-threads 0`."""
    argv = _run_and_capture(
        monkeypatch, tmp_path, gpu_enabled=False, params=["-crf", "20"]
    )
    assert "libx264" in argv  # CPU video codec applied
    assert _has_threads_zero(argv)


def test_nvenc_path_does_not_inject_threads(monkeypatch, tmp_path):
    """gpu_enabled=True -> NVENC encode, no `-threads` injected."""
    argv = _run_and_capture(
        monkeypatch,
        tmp_path,
        gpu_enabled=True,
        params=["-c:v", "libx264", "-crf", "20"],
    )
    assert "-threads" not in argv


def test_cpu_path_respects_preset_pinned_threads(monkeypatch, tmp_path):
    """A preset that already pins -threads is preserved; no extra `-threads 0`."""
    argv = _run_and_capture(
        monkeypatch,
        tmp_path,
        gpu_enabled=False,
        params=["-threads", "4", "-crf", "20"],
    )
    assert argv.count("-threads") == 1
    assert argv[argv.index("-threads") + 1] == "4"


def test_has_threads_helper():
    """The detection helper matches the exact `-threads` token only."""
    w = auto_render.RenderWorker.__new__(auto_render.RenderWorker)
    assert w._has_threads(["-threads", "0"]) is True
    assert w._has_threads(["-c:v", "libx264"]) is False
