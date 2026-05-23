"""Phase 3.4 — system monitor (best-effort, psutil-optional).

Returns a SystemSample dataclass with CPU% / free memory / GPU
temperature. Uses psutil if importable, falls back to None
values otherwise. GPU temp comes from pynvml (already a Phase 2d
dependency); failures degrade silently.

Pure-Python read. No state mutation. The QTimer wiring is in
auto_render.py — this module exposes only the pure sampler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("core.orchestration.system_monitor")


@dataclass(frozen=True)
class SystemSample:
    cpu_percent: Optional[float] = None
    memory_free_gb: Optional[float] = None
    memory_percent: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    error: Optional[str] = None

    def has_any(self) -> bool:
        return any(
            v is not None
            for v in (
                self.cpu_percent,
                self.memory_free_gb,
                self.memory_percent,
                self.gpu_temp_c,
            )
        )


def sample_system() -> SystemSample:
    """One snapshot. Best-effort; never raises."""
    cpu_percent: Optional[float] = None
    mem_free_gb: Optional[float] = None
    mem_pct: Optional[float] = None
    gpu_temp: Optional[float] = None
    err: Optional[str] = None

    try:
        import psutil  # type: ignore[import-not-found]

        try:
            cpu_percent = float(psutil.cpu_percent(interval=None))
        except Exception as exc:
            logger.debug("system_monitor: cpu probe failed: %s", exc)
        try:
            vm = psutil.virtual_memory()
            mem_free_gb = float(vm.available) / (1024**3)
            mem_pct = float(vm.percent)
        except Exception as exc:
            logger.debug("system_monitor: mem probe failed: %s", exc)
    except ImportError:
        err = "psutil not installed"
    except Exception as exc:
        err = f"psutil error: {exc}"

    # GPU temp via pynvml (already a Phase 2d dep).
    try:
        import pynvml  # type: ignore[import-not-found]

        try:
            pynvml.nvmlInit()
        except Exception:
            pynvml = None  # type: ignore[assignment]
        if pynvml is not None:
            try:
                count = pynvml.nvmlDeviceGetCount()
                if count > 0:
                    h = pynvml.nvmlDeviceGetHandleByIndex(0)
                    t = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                    gpu_temp = float(t)
            except Exception as exc:
                logger.debug("system_monitor: gpu temp probe failed: %s", exc)
            finally:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("system_monitor: pynvml error: %s", exc)

    return SystemSample(
        cpu_percent=cpu_percent,
        memory_free_gb=mem_free_gb,
        memory_percent=mem_pct,
        gpu_temp_c=gpu_temp,
        error=err,
    )


__all__ = ["SystemSample", "sample_system"]
