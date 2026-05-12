"""
Standalone benchmark tool for measuring ffmpeg commands.

Produces the numbers that drive 1vmo Suite Phase 1 NVENC migration decisions:
wall-clock time, output size, and (in full mode) VMAF quality for any ffmpeg
command against any input video. Not integrated into the GUI apps — invoked
manually by the developer.

Two modes:
    quick  - wall-clock + output size only (~10 sec overhead per run)
    full   - adds VMAF mean, 5th percentile, min, max (~60 sec overhead)

Usage examples:
    python bench.py --input clip.mp4 \\
        --preset-args "-c:v libx264 -preset medium -crf 20 -c:a copy" \\
        --mode quick

    python bench.py --input clip.mp4 \\
        --preset-args "-c:v h264_nvenc -preset p5 -rc vbr -cq 21 -c:a copy" \\
        --mode full --runs 3 --label nvenc_p5_cq21

Results land as JSON under bench_results/<label>__result.json, with encoded
outputs kept alongside for manual inspection.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from core import ffmpeg_runner as core_ffmpeg_runner

SCRIPT_DIR = Path(__file__).resolve().parent


def _find_executable(name: str) -> Optional[Path]:
    """Find ffmpeg/ffprobe using the same discovery rule as gpu_detect.py:
    first ./ffmpeg/, then PATH."""
    local = SCRIPT_DIR / "ffmpeg" / (f"{name}.exe" if os.name == "nt" else name)
    if local.is_file():
        return local
    from shutil import which

    hit = which(name)
    return Path(hit) if hit else None


def _creationflags() -> int:
    return core_ffmpeg_runner.hidden_creationflags()


def _sanitize_label(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned[:80] or "bench"


def _probe_input(ffprobe: Path, video: Path) -> dict:
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration,bit_rate",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(video),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=_creationflags(),
        check=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise RuntimeError(f"ffprobe found no video stream in {video}")
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or 0)
    bitrate_raw = fmt.get("bit_rate")
    bitrate_kbps = int(bitrate_raw) // 1000 if bitrate_raw else None
    return {
        "path": str(video),
        "duration_seconds": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "codec": video_stream.get("codec_name"),
        "bitrate_kbps": bitrate_kbps,
    }


def _ffmpeg_version(ffmpeg: Path) -> str:
    result = subprocess.run(
        [str(ffmpeg), "-version"],
        capture_output=True,
        text=True,
        creationflags=_creationflags(),
        check=False,
        timeout=10,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    first = combined.splitlines()[0] if combined.strip() else ""
    return first


def _drain(stream, sink: list) -> None:
    # Read a subprocess pipe to completion; keeps pipe buffer from blocking.
    for line in stream:
        sink.append(line)


def _run_encode(
    ffmpeg: Path, input_file: Path, preset_args_list: List[str], output_file: Path
) -> Tuple[float, int, Optional[str]]:
    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        "-progress",
        "pipe:1",
        "-i",
        str(input_file),
        *preset_args_list,
        str(output_file),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_creationflags(),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None and proc.stderr is not None

    stdout_lines: list = []
    stderr_lines: list = []
    t_out = threading.Thread(
        target=_drain, args=(proc.stdout, stdout_lines), daemon=True
    )
    t_err = threading.Thread(
        target=_drain, args=(proc.stderr, stderr_lines), daemon=True
    )

    start = time.perf_counter()
    t_out.start()
    t_err.start()
    proc.wait()
    t_out.join()
    t_err.join()
    elapsed = time.perf_counter() - start

    error: Optional[str] = None
    if proc.returncode != 0:
        error = ("".join(stderr_lines)).strip() or f"ffmpeg returned {proc.returncode}"

    output_bytes = output_file.stat().st_size if output_file.is_file() else 0
    return elapsed, output_bytes, error


def _escape_filter_path(p: Path) -> str:
    # libvmaf log_path sits inside an ffmpeg filter string with two escaping
    # layers. On Windows the drive-letter colon collides with the filter-
    # option ':' separator. Empirically, the working combination is BOTH
    # single-quote wrapping (at filtergraph level) AND backslash-escaping
    # the ':' (at filter-options level). Single-quotes alone are not enough;
    # backslash-escape alone is not enough. Caller wraps the returned string
    # in single quotes inside the filter expression.
    return str(p).replace("\\", "/").replace(":", "\\:")


def _run_vmaf(
    ffmpeg: Path, distorted: Path, reference: Path
) -> Tuple[dict, Optional[str]]:
    with tempfile.TemporaryDirectory(prefix="vmaf_") as tmpdir:
        log_path = Path(tmpdir) / "vmaf.json"
        filter_str = (
            "[0:v]setpts=PTS-STARTPTS[distorted];"
            "[1:v]setpts=PTS-STARTPTS[reference];"
            f"[distorted][reference]libvmaf=log_path='{_escape_filter_path(log_path)}':log_fmt=json"
        )
        cmd = [
            str(ffmpeg),
            "-hide_banner",
            "-i",
            str(distorted),
            "-i",
            str(reference),
            "-lavfi",
            filter_str,
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=_creationflags(),
            timeout=1800,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            tail = (
                stderr.splitlines()[-1]
                if stderr
                else f"libvmaf exited {result.returncode}"
            )
            return {}, tail
        if not log_path.is_file():
            return {}, "libvmaf produced no log file"
        with open(log_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    pooled = data.get("pooled_metrics", {}).get("vmaf", {})
    frames = data.get("frames", [])
    per_frame = [
        f.get("metrics", {}).get("vmaf")
        for f in frames
        if f.get("metrics", {}).get("vmaf") is not None
    ]
    if not per_frame:
        return {}, "libvmaf log had no per-frame vmaf metrics"
    per_frame_sorted = sorted(per_frame)
    p5_idx = int(0.05 * len(per_frame_sorted))
    return (
        {
            "vmaf_mean": pooled.get("mean"),
            "vmaf_p5": per_frame_sorted[p5_idx],
            "vmaf_min": pooled.get("min"),
            "vmaf_max": pooled.get("max"),
        },
        None,
    )


def _gpu_via_nvidia_smi() -> Optional[str]:
    """Best-effort GPU name via nvidia-smi. Returns None if not available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_creationflags(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [
        line.strip() for line in (result.stdout or "").splitlines() if line.strip()
    ]
    return lines[0] if lines else None


def _human_size(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _format_summary(result: dict, json_path: Path) -> str:
    inp = result["input"]
    lines: List[str] = []
    lines.append("=== BENCHMARK COMPLETE ===")
    lines.append(f"Label:        {result['label']}")
    lines.append(
        f"Input:        {inp['path']} ({inp['duration_seconds']:.1f}s, "
        f"{inp['width']}x{inp['height']}, {inp['codec']})"
    )
    lines.append(f"Mode:         {result['mode']}")
    lines.append(f"Runs:         {len(result['runs'])}")
    lines.append("")

    agg = result["aggregate"]
    runs = result["runs"]
    if len(runs) > 1:
        lines.append(
            f"Wall-clock:   {agg['wall_clock_mean']:.1f} sec  "
            f"(\u00b1{agg['wall_clock_stddev']:.2f})"
        )
        lines.append(f"Output size:  {_human_size(agg['output_bytes_mean'])}")
        if agg.get("vmaf_mean_avg") is not None:
            lines.append(f"VMAF mean:    {agg['vmaf_mean_avg']:.2f}")
        if agg.get("vmaf_p5_avg") is not None:
            lines.append(f"VMAF p5:      {agg['vmaf_p5_avg']:.2f}")
    else:
        r = runs[0]
        lines.append(f"Wall-clock:   {r['wall_clock_seconds']:.1f} sec")
        lines.append(f"Output size:  {_human_size(r['output_bytes'])}")
        if r.get("vmaf_mean") is not None:
            lines.append(f"VMAF mean:    {r['vmaf_mean']:.2f}")
        if r.get("vmaf_p5") is not None:
            lines.append(f"VMAF p5:      {r['vmaf_p5']:.2f}")
        if r.get("vmaf_min") is not None:
            lines.append(f"VMAF min:     {r['vmaf_min']:.2f}")

    lines.append("")
    lines.append(f"Result JSON:  {json_path}")
    for r in runs:
        if r.get("output_path"):
            lines.append(f"Output video: {r['output_path']}")

    failed = [r for r in runs if not r["encode_succeeded"]]
    if failed:
        lines.append("")
        lines.append(f"FAILED RUNS:  {len(failed)} of {len(runs)}")
        for r in failed:
            lines.append(f"  run {r['run_index']}: {r.get('error') or 'unknown error'}")

    if result.get("warning"):
        lines.append("")
        lines.append(f"Warning:      {result['warning']}")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bench.py",
        description=(
            "Benchmark an ffmpeg command. Measures wall-clock time, output "
            "size, and (in full mode) VMAF quality. Not integrated into the "
            "1vmo Suite apps — invoked manually by the developer."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input video file",
    )
    parser.add_argument(
        "--preset-args",
        required=True,
        help=(
            "Ffmpeg argument string between input and output. The tool "
            'prepends "-progress pipe:1 -i <input>" and appends an output '
            'filename. Example: "-c:v libx264 -preset medium -crf 20 -c:a copy"'
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="quick",
        help="quick: wall-clock + size (~10s overhead). full: adds VMAF (~60s overhead). (default: quick)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./bench_results"),
        help="Directory for encoded outputs and JSON result (default: ./bench_results/)",
    )
    parser.add_argument(
        "--label",
        help="Human-readable name for this run. Used in filenames and JSON. (default: derived from --preset-args)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of times to run the benchmark. Results are averaged, stddev reported when >1. (default: 1)",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        parser.error(f"input video not found: {args.input}")
    if args.runs < 1:
        parser.error("--runs must be >= 1")

    ffmpeg = _find_executable("ffmpeg")
    ffprobe = _find_executable("ffprobe")
    if ffmpeg is None:
        parser.error("ffmpeg not found in ./ffmpeg/ or on PATH")
    if ffprobe is None:
        parser.error("ffprobe not found in ./ffmpeg/ or on PATH")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    label = args.label or _sanitize_label(args.preset_args)
    preset_args_list = shlex.split(args.preset_args, posix=True)

    input_info = _probe_input(ffprobe, args.input)

    run_results: List[dict] = []
    warning: Optional[str] = None

    for run_idx in range(1, args.runs + 1):
        output_file = args.output_dir / f"{label}__run{run_idx}.mkv"
        elapsed, output_bytes, error = _run_encode(
            ffmpeg,
            args.input,
            preset_args_list,
            output_file,
        )

        entry = {
            "run_index": run_idx,
            "wall_clock_seconds": elapsed,
            "output_bytes": output_bytes,
            "output_path": str(output_file) if output_file.is_file() else None,
            "vmaf_mean": None,
            "vmaf_p5": None,
            "vmaf_min": None,
            "vmaf_max": None,
            "encode_succeeded": error is None,
            "error": error,
        }

        if error is None and args.mode == "full":
            vmaf_metrics, vmaf_err = _run_vmaf(ffmpeg, output_file, args.input)
            if vmaf_err:
                warning = f"VMAF measurement failed: {vmaf_err}"
            else:
                entry.update(vmaf_metrics)

        run_results.append(entry)

    wall_values = [r["wall_clock_seconds"] for r in run_results]
    size_values = [r["output_bytes"] for r in run_results]
    vmaf_mean_values = [
        r["vmaf_mean"] for r in run_results if r["vmaf_mean"] is not None
    ]
    vmaf_p5_values = [r["vmaf_p5"] for r in run_results if r["vmaf_p5"] is not None]

    aggregate = {
        "wall_clock_mean": statistics.mean(wall_values),
        "wall_clock_stddev": statistics.stdev(wall_values)
        if len(wall_values) > 1
        else 0.0,
        "output_bytes_mean": statistics.mean(size_values),
        "vmaf_mean_avg": statistics.mean(vmaf_mean_values)
        if vmaf_mean_values
        else None,
        "vmaf_p5_avg": statistics.mean(vmaf_p5_values) if vmaf_p5_values else None,
    }

    ffmpeg_command_display = " ".join(
        [
            str(ffmpeg),
            "-hide_banner",
            "-y",
            "-progress",
            "pipe:1",
            "-i",
            str(args.input),
            *preset_args_list,
            f"{label}__run<N>.mkv",
        ]
    )

    result = {
        "label": label,
        "mode": args.mode,
        "input": input_info,
        "preset_args": args.preset_args,
        "ffmpeg_command": ffmpeg_command_display,
        "ffmpeg_path": str(ffmpeg),
        "ffmpeg_version": _ffmpeg_version(ffmpeg),
        "runs": run_results,
        "aggregate": aggregate,
        "system": {
            "os": platform.platform(),
            "cpu": platform.processor() or None,
            "gpu": _gpu_via_nvidia_smi(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
    }
    if warning:
        result["warning"] = warning

    json_path = args.output_dir / f"{label}__result.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)

    print(_format_summary(result, json_path))

    return 0 if all(r["encode_succeeded"] for r in run_results) else 1


if __name__ == "__main__":
    sys.exit(main())
