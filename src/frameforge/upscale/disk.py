"""Disk and duration guards for the current on-disk PNG upscale pipeline.

This is not a streaming upscaler. ffmpeg still dumps every source frame as PNG,
ONNX writes 2× PNGs, then ffmpeg assembles. Peak temp is both trees at once.
"""

from __future__ import annotations

import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# RGB PNG worst-case: 3 bytes/pixel uncompressed + ~33% filter/deflate expansion.
PNG_BYTES_PER_PIXEL = 4.0
# Current ONNX path is 2× spatial.
UPSCALE_SCALE = 2
# Headroom for audio sidecar, checkpoint, filesystem slack.
SAFETY_MARGIN = 1.3
DEFAULT_MAX_DURATION_MINUTES = 15.0
DEFAULT_ORPHAN_HOURS = 24.0
TEMP_SKIP_DIRS = frozenset({"dl", "junk"})
FRAME_DIR_NAMES = ("frames", "upscaled_frames")


@dataclass(frozen=True)
class VideoMetrics:
    width: int
    height: int
    fps: float
    duration_sec: float


class DiskSpaceError(RuntimeError):
    """Refused before extract: estimated PNG temp would exceed free space."""

    category = "disk_space"

    def __init__(
        self,
        *,
        estimated_bytes: int,
        required_bytes: int,
        free_bytes: int,
        volume: str,
        margin: float,
        frames: int,
        width: int,
        height: int,
    ) -> None:
        self.estimated_bytes = int(estimated_bytes)
        self.required_bytes = int(required_bytes)
        self.free_bytes = int(free_bytes)
        self.volume = volume
        self.margin = float(margin)
        self.frames = int(frames)
        self.width = int(width)
        self.height = int(height)
        super().__init__(
            "Not enough disk space for upscale PNG frames: "
            f"need {format_bytes(self.required_bytes)} "
            f"(estimate {format_bytes(self.estimated_bytes)} × {self.margin:g}), "
            f"{format_bytes(self.free_bytes)} free on {self.volume}."
        )

    def option_patch(self) -> dict[str, Any]:
        return {
            "disk_estimated_bytes": self.estimated_bytes,
            "disk_required_bytes": self.required_bytes,
            "disk_free_bytes": self.free_bytes,
            "disk_volume": self.volume,
            "disk_frames": self.frames,
            "disk_width": self.width,
            "disk_height": self.height,
        }


class UpscaleDurationError(RuntimeError):
    """Refused before extract: clip longer than the PNG-pipeline duration cap."""

    category = "upscale_limit"

    def __init__(self, *, duration_sec: float, max_minutes: float) -> None:
        self.duration_sec = float(duration_sec)
        self.max_minutes = float(max_minutes)
        super().__init__(
            "Upscale refused: clip is "
            f"{self.duration_sec / 60.0:.1f} min, max allowed is {self.max_minutes:g} min "
            "until streaming upscale ships."
        )

    def option_patch(self) -> dict[str, Any]:
        return {
            "upscale_duration_sec": self.duration_sec,
            "upscale_max_duration_min": self.max_minutes,
        }


def format_bytes(n: int | float) -> str:
    value = float(max(0, n))
    for unit, size in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{int(value)} B"


def frame_count(duration_sec: float, fps: float, max_frames: int | None = None) -> int:
    n = max(1, int(math.ceil(max(0.0, duration_sec) * max(1.0, fps))))
    if max_frames is not None:
        n = min(n, max(0, int(max_frames)))
    return max(1, n)


def estimate_png_pipeline_bytes(
    *,
    width: int,
    height: int,
    frames: int,
    scale: int = UPSCALE_SCALE,
    bytes_per_pixel: float = PNG_BYTES_PER_PIXEL,
) -> int:
    """Peak bytes: source PNGs + 2× upscaled PNGs (both live until mux)."""
    w = max(1, int(width))
    h = max(1, int(height))
    n = max(1, int(frames))
    s = max(1, int(scale))
    src = n * w * h * bytes_per_pixel
    dst = n * (w * s) * (h * s) * bytes_per_pixel
    return int(src + dst)


def video_metrics(path: Path, *, probe_data: dict | None = None) -> VideoMetrics:
    from frameforge.upscale.ffmpeg_utils import probe

    data = probe_data if probe_data is not None else probe(Path(path))
    width = height = 0
    fps = 25.0
    for stream in data.get("streams") or []:
        if stream.get("codec_type") != "video":
            continue
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "25/1"
        if isinstance(rate, str) and "/" in rate:
            num, den = rate.split("/", 1)
            den_f = float(den) or 1.0
            fps = max(1.0, float(num) / den_f)
        else:
            fps = max(1.0, float(rate or 25))
        break
    duration = 0.0
    fmt = data.get("format") or {}
    raw = fmt.get("duration")
    if raw not in (None, "N/A", ""):
        try:
            duration = float(raw)
        except (TypeError, ValueError):
            duration = 0.0
    if duration <= 0:
        for stream in data.get("streams") or []:
            if stream.get("codec_type") != "video":
                continue
            raw = stream.get("duration")
            if raw not in (None, "N/A", ""):
                try:
                    duration = float(raw)
                except (TypeError, ValueError):
                    duration = 0.0
            break
    if duration <= 0:
        duration = 1.0
    if width <= 0 or height <= 0:
        raise RuntimeError(f"No video stream in {path}")
    return VideoMetrics(width=width, height=height, fps=fps, duration_sec=duration)


def free_bytes_for(path: Path) -> int:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return int(shutil.disk_usage(path).free)


def assert_upscale_guards(
    metrics: VideoMetrics,
    *,
    max_frames: int | None = None,
    max_duration_minutes: float | None = DEFAULT_MAX_DURATION_MINUTES,
    free_bytes: int,
    volume: str,
    safety_margin: float = SAFETY_MARGIN,
    scale: int = UPSCALE_SCALE,
) -> dict[str, int | float | str]:
    """Refuse duration-over-cap or insufficient free space. Does not extract frames."""
    if max_duration_minutes is not None and float(max_duration_minutes) > 0:
        cap_sec = float(max_duration_minutes) * 60.0
        if metrics.duration_sec > cap_sec + 0.5:
            raise UpscaleDurationError(
                duration_sec=metrics.duration_sec,
                max_minutes=float(max_duration_minutes),
            )
    frames = frame_count(metrics.duration_sec, metrics.fps, max_frames=max_frames)
    estimated = estimate_png_pipeline_bytes(
        width=metrics.width,
        height=metrics.height,
        frames=frames,
        scale=scale,
    )
    required = int(math.ceil(estimated * float(safety_margin)))
    if required > int(free_bytes):
        raise DiskSpaceError(
            estimated_bytes=estimated,
            required_bytes=required,
            free_bytes=int(free_bytes),
            volume=volume,
            margin=float(safety_margin),
            frames=frames,
            width=metrics.width,
            height=metrics.height,
        )
    return {
        "frames": frames,
        "estimated_bytes": estimated,
        "required_bytes": required,
        "free_bytes": int(free_bytes),
        "volume": volume,
    }


def cleanup_job_frames(base: Path, *, include_job_dir: bool = False) -> None:
    """Delete PNG trees for one upscale job. Never touches temp/dl."""
    base = Path(base)
    for name in FRAME_DIR_NAMES:
        folder = base / name
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    if include_job_dir and base.is_dir():
        shutil.rmtree(base, ignore_errors=True)


def sweep_orphan_frame_dirs(temp_root: Path, *, max_age_hours: float = DEFAULT_ORPHAN_HOURS) -> int:
    """Remove stale temp/<job>/{frames,upscaled_frames}. Skips temp/dl and temp/junk."""
    temp_root = Path(temp_root)
    if not temp_root.is_dir():
        return 0
    cutoff = time.time() - max(0.0, float(max_age_hours)) * 3600.0
    removed = 0
    for child in list(temp_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.lower() in TEMP_SKIP_DIRS:
            continue
        for name in FRAME_DIR_NAMES:
            folder = child / name
            if not folder.is_dir():
                continue
            try:
                mtime = folder.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
