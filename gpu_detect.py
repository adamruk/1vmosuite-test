"""
GPU capability detection for 1vmo Suite.

Runs at app startup to determine which NVENC encoders are usable on this
system, so the UI can surface GPU-accelerated preset groups when available
and hide them cleanly when not.

Two-signal detection:
  1. pynvml  — identifies NVIDIA hardware: model, generation, driver, VRAM
  2. ffmpeg  — enumerates actual NVENC encoders exposed by THIS ffmpeg build

A capability is unlocked only if both signals agree. If pynvml is missing
or no NVIDIA GPU is present, detection returns a "no GPU" result and the
app falls back to CPU-only behavior.

Generation classification uses CUDA compute capability rather than parsing
marketing names:
  7.5        -> Turing      (RTX 20xx, GTX 16xx)      H.264, HEVC
  8.0/8.6/8.7 -> Ampere     (RTX 30xx)                H.264, HEVC
  8.9        -> Ada Lovelace (RTX 40xx)               H.264, HEVC, AV1
  9.0+       -> Hopper/Blackwell/newer                H.264, HEVC, AV1 (assumed)

Reference: FFMPEG_CPU_TO_NVENC_REFERENCE.md, sections 2 and 9.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from core import ffmpeg_runner as core_ffmpeg_runner


class GPUGeneration(Enum):
    UNKNOWN = "unknown"
    PRE_TURING = "pre_turing"
    TURING = "turing"
    AMPERE = "ampere"
    ADA = "ada_lovelace"
    BLACKWELL = "blackwell_or_newer"

    @property
    def supports_av1(self) -> bool:
        return self in (GPUGeneration.ADA, GPUGeneration.BLACKWELL)

    @property
    def supports_hevc(self) -> bool:
        return self in (
            GPUGeneration.TURING,
            GPUGeneration.AMPERE,
            GPUGeneration.ADA,
            GPUGeneration.BLACKWELL,
        )

    @property
    def display_name(self) -> str:
        return {
            GPUGeneration.UNKNOWN: "Unknown",
            GPUGeneration.PRE_TURING: "Pre-Turing",
            GPUGeneration.TURING: "Turing",
            GPUGeneration.AMPERE: "Ampere",
            GPUGeneration.ADA: "Ada Lovelace",
            GPUGeneration.BLACKWELL: "Blackwell (or newer)",
        }[self]


@dataclass
class NvencCodecs:
    h264: bool = False
    hevc: bool = False
    av1: bool = False

    @property
    def any_available(self) -> bool:
        return self.h264 or self.hevc or self.av1


@dataclass
class GPUDevice:
    index: int
    name: str
    generation: GPUGeneration
    compute_capability: Optional[Tuple[int, int]] = None
    vram_total_mb: Optional[int] = None

    def short_description(self) -> str:
        vram = f", {self.vram_total_mb // 1024} GB VRAM" if self.vram_total_mb else ""
        cc = (
            f" (CC {self.compute_capability[0]}.{self.compute_capability[1]})"
            if self.compute_capability
            else ""
        )
        return f"{self.name} — {self.generation.display_name}{cc}{vram}"


@dataclass
class GPUCapabilities:
    has_nvidia: bool = False
    devices: List[GPUDevice] = field(default_factory=list)
    ffmpeg_codecs: NvencCodecs = field(default_factory=NvencCodecs)
    driver_version: Optional[str] = None
    pynvml_available: bool = False
    error: Optional[str] = None

    nvenc_available: bool = False
    h264_available: bool = False
    hevc_available: bool = False
    av1_available: bool = False

    @property
    def primary_device(self) -> Optional[GPUDevice]:
        return self.devices[0] if self.devices else None


def _classify_by_compute(major: int, minor: int) -> GPUGeneration:
    if major < 7 or (major == 7 and minor < 5):
        return GPUGeneration.PRE_TURING
    if (major, minor) == (7, 5):
        return GPUGeneration.TURING
    if major == 8 and minor in (0, 6, 7):
        return GPUGeneration.AMPERE
    if (major, minor) == (8, 9):
        return GPUGeneration.ADA
    if major >= 9:
        return GPUGeneration.BLACKWELL
    return GPUGeneration.UNKNOWN


def _probe_pynvml() -> Tuple[List[GPUDevice], Optional[str], Optional[str]]:
    """Return (devices, driver_version, error_message). Never raises."""
    try:
        import pynvml
    except ImportError:
        return [], None, "pynvml not installed — GPU features disabled"

    try:
        # Per FFMPEG_CPU_TO_NVENC_REFERENCE.md §9: bare nvmlInit() is the
        # v2 implementation in nvidia-ml-py 13.x+. Do NOT use nvmlInit_v2.
        pynvml.nvmlInit()
    except Exception as exc:
        return [], None, f"NVML init failed: {exc}"

    devices: List[GPUDevice] = []
    driver_version: Optional[str] = None
    error: Optional[str] = None

    try:
        try:
            driver_raw = pynvml.nvmlSystemGetDriverVersion()
            driver_version = (
                driver_raw.decode() if isinstance(driver_raw, bytes) else driver_raw
            )
        except Exception:
            pass

        count = pynvml.nvmlDeviceGetCount()
        for idx in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)

            name_raw = pynvml.nvmlDeviceGetName(handle)
            name = name_raw.decode() if isinstance(name_raw, bytes) else name_raw

            compute_cap: Optional[Tuple[int, int]] = None
            try:
                major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                compute_cap = (major, minor)
                generation = _classify_by_compute(major, minor)
            except Exception:
                generation = GPUGeneration.UNKNOWN

            vram_mb: Optional[int] = None
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_mb = int(mem.total / (1024 * 1024))
            except Exception:
                pass

            devices.append(
                GPUDevice(
                    index=idx,
                    name=name,
                    generation=generation,
                    compute_capability=compute_cap,
                    vram_total_mb=vram_mb,
                )
            )

        if not devices:
            error = "No NVIDIA GPUs detected"
    except Exception as exc:
        error = f"NVML query failed: {exc}"
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass

    return devices, driver_version, error


_NVENC_LINE = re.compile(
    r"^\s*V[A-Z.]+\s+(h264_nvenc|hevc_nvenc|av1_nvenc)\b", re.MULTILINE
)


def _probe_ffmpeg_encoders(ffmpeg_path: Path) -> Tuple[NvencCodecs, Optional[str]]:
    codecs = NvencCodecs()

    if not ffmpeg_path.is_file():
        return codecs, f"ffmpeg not found at {ffmpeg_path}"

    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=core_ffmpeg_runner.hidden_creationflags(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return codecs, "ffmpeg -encoders timed out"
    except Exception as exc:
        return codecs, f"ffmpeg probe failed: {exc}"

    haystack = (result.stdout or "") + (result.stderr or "")
    for match in _NVENC_LINE.finditer(haystack):
        enc = match.group(1)
        if enc == "h264_nvenc":
            codecs.h264 = True
        elif enc == "hevc_nvenc":
            codecs.hevc = True
        elif enc == "av1_nvenc":
            codecs.av1 = True

    return codecs, None


def detect(ffmpeg_path: Path) -> GPUCapabilities:
    """Run full detection and return a GPUCapabilities result. Safe at startup."""
    caps = GPUCapabilities()

    devices, driver_version, nvml_error = _probe_pynvml()
    caps.devices = devices
    caps.driver_version = driver_version
    caps.pynvml_available = nvml_error != "pynvml not installed — GPU features disabled"
    caps.has_nvidia = len(devices) > 0

    codecs, ffmpeg_error = _probe_ffmpeg_encoders(ffmpeg_path)
    caps.ffmpeg_codecs = codecs

    if nvml_error and not caps.has_nvidia:
        caps.error = nvml_error
    elif ffmpeg_error:
        caps.error = ffmpeg_error

    if caps.has_nvidia:
        primary = caps.primary_device
        gen = primary.generation if primary else GPUGeneration.UNKNOWN
        hw_supports_hevc = gen.supports_hevc or gen == GPUGeneration.UNKNOWN
        # H.264 NVENC is supported by every NVENC-era NVIDIA GPU, so it unlocks
        # from the ffmpeg probe alone — independent of the HEVC hardware gate.
        # (A4: previously `hw_supports_hevc and codecs.h264`, which wrongly hid
        # H.264 on pre-Turing cards that lack HEVC NVENC but do support H.264.)
        caps.h264_available = codecs.h264
        caps.hevc_available = hw_supports_hevc and codecs.hevc
        caps.av1_available = gen.supports_av1 and codecs.av1
        caps.nvenc_available = (
            caps.h264_available or caps.hevc_available or caps.av1_available
        )

    return caps


def format_status(caps: GPUCapabilities) -> str:
    """One-line human-readable status suitable for a status bar."""
    if not caps.has_nvidia:
        return f"GPU: not available ({caps.error or 'no NVIDIA GPU detected'})"

    primary = caps.primary_device
    assert primary is not None

    codecs = []
    if caps.h264_available:
        codecs.append("H.264")
    if caps.hevc_available:
        codecs.append("HEVC")
    if caps.av1_available:
        codecs.append("AV1")
    codec_str = "/".join(codecs) if codecs else "none"

    driver = f", driver {caps.driver_version}" if caps.driver_version else ""
    return f"OK GPU: {primary.name} ({primary.generation.display_name}){driver} - NVENC: {codec_str}"


def format_detailed_report(caps: GPUCapabilities) -> str:
    """Multi-line diagnostic report for a help dialog or log."""
    lines: List[str] = []
    lines.append("=== GPU Detection Report ===")

    if not caps.pynvml_available:
        lines.append("pynvml: NOT INSTALLED")
    else:
        lines.append(f"pynvml: available (driver {caps.driver_version or 'unknown'})")

    if caps.has_nvidia:
        lines.append(f"NVIDIA GPUs detected: {len(caps.devices)}")
        for dev in caps.devices:
            lines.append(f"  [{dev.index}] {dev.short_description()}")
    else:
        lines.append(f"NVIDIA GPUs detected: 0 ({caps.error or 'unknown reason'})")

    fc = caps.ffmpeg_codecs
    lines.append(
        f"FFmpeg NVENC encoders: "
        f"h264_nvenc={'yes' if fc.h264 else 'no'}, "
        f"hevc_nvenc={'yes' if fc.hevc else 'no'}, "
        f"av1_nvenc={'yes' if fc.av1 else 'no'}"
    )

    lines.append("")
    lines.append("Unlocked capabilities (hardware AND ffmpeg):")
    lines.append(f"  H.264 NVENC: {'yes' if caps.h264_available else 'no'}")
    lines.append(f"  HEVC NVENC:  {'yes' if caps.hevc_available else 'no'}")
    lines.append(f"  AV1 NVENC:   {'yes' if caps.av1_available else 'no'}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    script_dir = Path(__file__).resolve().parent
    ffmpeg = script_dir / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")

    if len(sys.argv) > 1:
        ffmpeg = Path(sys.argv[1])

    caps = detect(ffmpeg)
    print(format_detailed_report(caps))
    print()
    print("Status line:")
    print(" ", format_status(caps))
