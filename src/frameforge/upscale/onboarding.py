"""Pure-data onboarding context for the upscale pre-job flow.

This module intentionally does NOT import Flet so it can be used from worker
threads and tests without requiring the GUI stack.  The Flet dialog that
presents this context lives in
``frameforge.ui_flet.components.upscale_onboarding``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OnboardingContext:
    """All information shown in the upscale onboarding dialog."""

    source_name: str
    width: int
    height: int
    duration_sec: float
    total_frames: int
    fps_source: float
    estimate_label: str
    fps_estimate: float
    probe_used: bool
    exceeds_gate: bool
    model_kind: str          # "smoke" | "realesrgan" | "resize" | "none" | "unknown"
    model_available: bool
    cpu_percent: float | None = None
    ram_percent: float | None = None
    segment_minutes: float = 15.0


def build_onboarding_context(
    source: "Path",  # noqa: F821
    *,
    estimate: "UpscaleEstimate",  # noqa: F821
    model_status_dict: dict,
    resource_reading: object | None = None,
    segment_minutes: float = 15.0,
) -> OnboardingContext:
    """Factory: build OnboardingContext from pipeline objects.

    Parameters
    ----------
    source:
        Path to the source video.
    estimate:
        ``UpscaleEstimate`` from ``frameforge.upscale.estimate``.
    model_status_dict:
        Dict from ``frameforge.upscale.onnx_upscaler.model_status()``.
    resource_reading:
        Optional ``ResourceReading`` from the sampler; None if unavailable.
    segment_minutes:
        Minutes per segment for the split suggestion.
    """
    from pathlib import Path

    src = Path(source)
    kind = str(model_status_dict.get("kind") or "none")
    available = bool(model_status_dict.get("available"))

    from frameforge.upscale.disk import video_metrics

    metrics = video_metrics(src)

    cpu: float | None = None
    ram: float | None = None
    if resource_reading is not None and getattr(resource_reading, "ok", False):
        cpu = float(resource_reading.cpu_percent)  # type: ignore[attr-defined]
        ram = float(resource_reading.ram_percent)  # type: ignore[attr-defined]

    return OnboardingContext(
        source_name=src.name,
        width=metrics.width,
        height=metrics.height,
        duration_sec=metrics.duration_sec,
        total_frames=estimate.total_frames,
        fps_source=metrics.fps,
        estimate_label=estimate.label,
        fps_estimate=estimate.fps_estimate,
        probe_used=estimate.probe_used,
        exceeds_gate=estimate.exceeds_gate,
        model_kind=kind,
        model_available=available,
        cpu_percent=cpu,
        ram_percent=ram,
        segment_minutes=segment_minutes,
    )
