"""Upscale completion time estimation and 4-hour gate policy.

Estimation strategy:
1. If a prior calibration fps value is stored (from a previous probe), use it.
2. Otherwise run a short probe (3 frames) through the ONNX upscaler to measure
   actual throughput on the current hardware.
3. Fall back to conservative table-based estimates when neither is available.

The 4-hour gate blocks automatic full-file upscale when the estimate exceeds
``FOUR_HOUR_GATE_SECONDS``.  The user must explicitly acknowledge and choose
either to proceed or to split into ~15-minute segments.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frameforge.upscale.disk import VideoMetrics

log = logging.getLogger(__name__)

FOUR_HOUR_GATE_SECONDS: float = 4.0 * 3600.0  # 14 400 s

# Conservative fallback fps estimates by pixel count bracket (pixels / frame).
# These are pessimistic on purpose — err on the side of warning the user.
_FPS_FALLBACK_TABLE: list[tuple[int, float]] = [
    # (max_pixels_per_frame, estimated_upscale_fps)
    (320 * 240, 8.0),    # QVGA and below
    (640 * 480, 4.0),    # SD
    (1280 * 720, 1.5),   # 720p
    (1920 * 1080, 0.6),  # 1080p — Radeon 680M / DirectML ballpark
    (2560 * 1440, 0.25), # 1440p
    (3840 * 2160, 0.10), # 4K (blocked upstream but listed for completeness)
]
_FPS_FALLBACK_DEFAULT = 0.4


@dataclass(frozen=True)
class UpscaleEstimate:
    total_frames: int
    fps_estimate: float
    total_seconds: float
    exceeds_gate: bool
    label: str
    probe_used: bool


def _fallback_fps(width: int, height: int) -> float:
    pixels = max(1, int(width)) * max(1, int(height))
    for max_px, fps in _FPS_FALLBACK_TABLE:
        if pixels <= max_px:
            return fps
    return _FPS_FALLBACK_DEFAULT


def probe_upscale_fps(
    model_path: Path | None,
    *,
    width: int,
    height: int,
    tile: int = 128,
    n_frames: int = 3,
    tmp_dir: Path | None = None,
) -> float | None:
    """Run N tiny synthetic frames through the ONNX upscaler to measure fps.

    Returns fps (float) or None when the model is unavailable or probe fails.
    The probe frames are tiny placeholders sized to the real resolution so that
    tile-splitting and provider selection match real job conditions.
    """
    try:
        import numpy as np

        from frameforge.upscale.onnx_upscaler import OnnxUpscaler
    except ImportError:
        return None

    try:
        upscaler = OnnxUpscaler(model_path=model_path, tile=tile)
        if not upscaler.available:
            return None

        import tempfile

        td = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="ff_probe_"))
        frames_dir = td / "probe_frames"
        out_dir = td / "probe_out"
        frames_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        from PIL import Image

        frame_paths: list[Path] = []
        for i in range(n_frames):
            img = Image.fromarray(
                np.zeros((max(4, height), max(4, width), 3), dtype=np.uint8), mode="RGB"
            )
            p = frames_dir / f"frame_{i:06d}.png"
            img.save(p)
            frame_paths.append(p)

        t0 = time.perf_counter()
        upscaler.upscale_frames(frame_paths, out_dir)
        elapsed = time.perf_counter() - t0
        if elapsed <= 0:
            return None
        fps = n_frames / elapsed
        log.info("Upscale probe: %.2f fps at %dx%d (tile=%d)", fps, width, height, tile)
        return fps
    except Exception as exc:  # noqa: BLE001
        log.debug("Upscale probe failed: %s", exc)
        return None


def estimate_upscale(
    metrics: "VideoMetrics",
    *,
    chunk_frames: int = 128,
    model_path: Path | None = None,
    tile: int = 128,
    cached_fps: float | None = None,
    run_probe: bool = True,
    tmp_dir: Path | None = None,
) -> UpscaleEstimate:
    """Return a time estimate for upscaling ``metrics``.

    Priority: cached_fps → probe → fallback table.
    """
    from frameforge.upscale.disk import frame_count

    total_frames = frame_count(metrics.duration_sec, metrics.fps)
    probe_used = False

    fps: float | None = cached_fps
    if fps is None and run_probe:
        fps = probe_upscale_fps(
            model_path,
            width=metrics.width,
            height=metrics.height,
            tile=tile,
            tmp_dir=tmp_dir,
        )
        if fps is not None:
            probe_used = True

    if fps is None or fps <= 0:
        fps = _fallback_fps(metrics.width, metrics.height)

    total_seconds = total_frames / max(fps, 0.001)
    exceeds = total_seconds > FOUR_HOUR_GATE_SECONDS

    return UpscaleEstimate(
        total_frames=total_frames,
        fps_estimate=fps,
        total_seconds=total_seconds,
        exceeds_gate=exceeds,
        label=format_estimate_label(total_seconds),
        probe_used=probe_used,
    )


def format_estimate_label(total_seconds: float) -> str:
    """Human-readable estimate label."""
    if total_seconds < 60:
        return f"~{int(total_seconds)}s"
    if total_seconds < 3600:
        mins = total_seconds / 60.0
        return f"~{mins:.0f} min"
    hours = total_seconds / 3600.0
    if hours < 2:
        mins = (total_seconds % 3600) / 60.0
        return f"~{int(hours)}h {int(mins)}m"
    return f"~{hours:.1f} hours"


def gate_message(estimate: UpscaleEstimate, *, source_name: str = "this clip") -> str:
    """Return a human-readable message for the >4h gate."""
    return (
        f"Estimated upscale time for {source_name}: {estimate.label} "
        f"({estimate.total_frames:,} frames at {estimate.fps_estimate:.2f} fps). "
        "That exceeds the 4-hour threshold. Running the full file on an iGPU "
        "could occupy your machine overnight with no guarantee of completion.\n\n"
        "Recommended: split into ~15-minute segments, upscale each sequentially, "
        "then stitch back into one remastered file."
    )
