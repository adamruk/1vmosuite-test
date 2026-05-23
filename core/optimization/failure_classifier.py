"""Phase 3.3 — regex-based ffmpeg-error → Recommendation mapper.

Pure function. Given an error_message string (the same string
Phase 3.1's QueueTask.error_message holds), return a Recommendation
explaining how the user could retry. UNKNOWN when no pattern
matches — we never guess. The user can always retry manually.
"""

from __future__ import annotations

import re
from typing import Optional

from core.optimization.recommendation_models import (
    Confidence,
    Recommendation,
    RecommendationKind,
)

# Each entry: (compiled regex, kind, confidence, reason, proposed_params).
_PATTERNS: list[tuple] = [
    (
        re.compile(r"no such file or directory", re.IGNORECASE),
        RecommendationKind.DEBUG_LOG,
        Confidence.HIGH,
        "Input file disappeared between selection and dispatch. "
        "Re-add the file and retry.",
        {},
    ),
    (
        re.compile(r"cannot allocate memory|out of memory", re.IGNORECASE),
        RecommendationKind.RETRY_AS_IS,
        Confidence.MEDIUM,
        "ffmpeg ran out of memory. Reduce parallel render count and retry.",
        {"num_threads_delta": -1},
    ),
    (
        re.compile(r"encoder.*?(not found|experimental)", re.IGNORECASE),
        RecommendationKind.SWITCH_ENCODER,
        Confidence.HIGH,
        "Requested encoder is unavailable or experimental in this "
        "ffmpeg build. Try a CPU codec instead.",
        {"gpu_enabled": False},
    ),
    (
        re.compile(r"nvenc.*?(out of sessions|capability check)", re.IGNORECASE),
        RecommendationKind.USE_CPU,
        Confidence.HIGH,
        "NVENC ran out of sessions or failed a capability check. Retry on CPU.",
        {"gpu_enabled": False},
    ),
    (
        re.compile(r"driver does not support", re.IGNORECASE),
        RecommendationKind.SWITCH_ENCODER,
        Confidence.HIGH,
        "GPU driver does not support the requested NVENC codec. "
        "Try hevc_nvenc or fall back to CPU.",
        {"gpu_codec": "hevc_nvenc"},
    ),
    (
        re.compile(r"(timeout|timed out|i/?o error)", re.IGNORECASE),
        RecommendationKind.RETRY_AS_IS,
        Confidence.MEDIUM,
        "Transient I/O failure. Retrying without changes is usually safe.",
        {},
    ),
    (
        re.compile(r"cannot load .*nv(cuda|encode)", re.IGNORECASE),
        RecommendationKind.USE_CPU,
        Confidence.HIGH,
        "NVIDIA CUDA/encode runtime not loadable. Disable GPU encoding for this batch.",
        {"gpu_enabled": False},
    ),
    (
        re.compile(r"initializeencoder failed", re.IGNORECASE),
        RecommendationKind.SWITCH_ENCODER,
        Confidence.MEDIUM,
        "NVENC encoder init failed; try a less aggressive preset "
        "family or fall back to CPU.",
        {"gpu_preset": "p4"},
    ),
]


def classify_failure(error_message: Optional[str]) -> Recommendation:
    """Map an error_message to a Recommendation.

    Returns a UNKNOWN-kind recommendation if no pattern matches.
    Never raises. The caller wraps the result in a dialog (Phase
    3.3 FailureSuggestionDialog) so the user can review before
    any retry.
    """
    text = (error_message or "").strip()
    if not text:
        return Recommendation(
            kind=RecommendationKind.UNKNOWN,
            reason="No error message captured. Inspect the ffmpeg "
            "log for context, then retry manually.",
            confidence=Confidence.LOW,
        )
    for pattern, kind, conf, reason, params in _PATTERNS:
        if pattern.search(text):
            return Recommendation(
                kind=kind,
                reason=reason,
                confidence=conf,
                delta_summary="see proposed_params",
                proposed_params=dict(params),
            )
    return Recommendation(
        kind=RecommendationKind.UNKNOWN,
        reason="No known pattern matched this error. Inspect the "
        "ffmpeg log for context, then retry manually.",
        confidence=Confidence.LOW,
    )


__all__ = ["classify_failure"]
