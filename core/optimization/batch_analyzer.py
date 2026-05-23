"""Phase 3.3 — batch-level health summary.

Given a list of (ScoreResult, render_duration) pairs, compute a
small BatchSummary the UI can show as a header banner. Pure
function. No I/O.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BatchSummary:
    """Aggregate health across a batch of rendered tasks."""

    total: int = 0
    green: int = 0
    yellow: int = 0
    red: int = 0
    unknown: int = 0
    failed: int = 0

    median_duration_s: Optional[float] = None
    slowest_duration_s: Optional[float] = None
    fastest_duration_s: Optional[float] = None

    # VMAF mean across green/yellow rows (None if no rows).
    avg_vmaf_mean: Optional[float] = None
    # pHash avg across rows where pHash was computed.
    avg_phash_distance: Optional[float] = None

    # Most common error_message (truncated). Empty if no failures.
    most_common_error: str = ""

    notes: list[str] = field(default_factory=list)


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    n = len(values)
    if n % 2 == 1:
        return values[n // 2]
    return (values[n // 2 - 1] + values[n // 2]) / 2.0


def analyze_batch(
    *,
    rows: list[dict],
    vmaf_mean_threshold: float = 96.0,
    phash_too_similar: float = 5.0,
) -> BatchSummary:
    """Aggregate health across rendered tasks.

    Args:
        rows: list of dicts shaped {
            "vmaf_mean": Optional[float],
            "vmaf_p5": Optional[float],
            "phash_avg_distance": Optional[float],
            "duration_s": Optional[float],
            "status": str  # "completed" / "failed" / ...
            "error_message": Optional[str],
        }

    Returns a BatchSummary suitable for the RenderHealthDialog
    header banner.
    """
    summary = BatchSummary(total=len(rows))
    durations: list[float] = []
    vmafs: list[float] = []
    phashes: list[float] = []
    errors: Counter = Counter()
    too_close_count = 0
    quality_below_count = 0

    for row in rows:
        status = (row.get("status") or "").lower()
        if status == "failed":
            summary.failed += 1
            err = (row.get("error_message") or "").strip()
            if err:
                # Truncate so a long ffmpeg log line doesn't poison
                # the counter key.
                errors[err[:120]] += 1
            continue

        d = row.get("duration_s")
        if isinstance(d, (int, float)) and d > 0:
            durations.append(float(d))

        vmaf_mean = row.get("vmaf_mean")
        if vmaf_mean is not None:
            try:
                vmafs.append(float(vmaf_mean))
                if float(vmaf_mean) < vmaf_mean_threshold:
                    quality_below_count += 1
            except (TypeError, ValueError):
                pass

        ph = row.get("phash_avg_distance")
        if ph is not None:
            try:
                ph_f = float(ph)
                phashes.append(ph_f)
                if ph_f < phash_too_similar:
                    too_close_count += 1
            except (TypeError, ValueError):
                pass

        # Health bucketing.
        if vmaf_mean is None and ph is None:
            summary.unknown += 1
        elif vmaf_mean is not None and float(vmaf_mean) < (vmaf_mean_threshold - 6.0):
            summary.red += 1
        elif (vmaf_mean is not None and float(vmaf_mean) < vmaf_mean_threshold) or (
            ph is not None and float(ph) < phash_too_similar
        ):
            summary.yellow += 1
        else:
            summary.green += 1

    summary.median_duration_s = _median(durations)
    summary.slowest_duration_s = max(durations) if durations else None
    summary.fastest_duration_s = min(durations) if durations else None
    summary.avg_vmaf_mean = (sum(vmafs) / len(vmafs)) if vmafs else None
    summary.avg_phash_distance = (sum(phashes) / len(phashes)) if phashes else None

    if errors:
        summary.most_common_error = errors.most_common(1)[0][0]

    if quality_below_count:
        summary.notes.append(
            f"{quality_below_count} of {summary.total} renders below VMAF "
            f"{vmaf_mean_threshold:.0f} — review them."
        )
    if too_close_count:
        summary.notes.append(
            f"{too_close_count} of {summary.total} have pHash < "
            f"{phash_too_similar:.0f} (close to source)."
        )
    if (
        summary.median_duration_s
        and summary.slowest_duration_s
        and summary.median_duration_s > 0
        and summary.slowest_duration_s > summary.median_duration_s * 2.0
    ):
        summary.notes.append(
            f"Slowest render {summary.slowest_duration_s:.0f}s vs "
            f"median {summary.median_duration_s:.0f}s — consider GPU."
        )
    return summary


__all__ = ["BatchSummary", "analyze_batch"]
