"""Split a source video into fixed-duration segments for sequential upscaling.

Each segment lands in its own unique subfolder under the FrameForge temp tree
so the upscale pipeline can process them independently with full checkpoint/
resume support.

Segment naming:
    <temp_root>/<source_stem>_<timestamp>_segments/seg_NNNN/seg_NNNN.mp4

After all segments are upscaled the remaster module can stitch them back.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

from frameforge.upscale.ffmpeg_utils import probe, run_cmd

log = logging.getLogger(__name__)

DEFAULT_SEGMENT_MINUTES: float = 15.0
_SAFE_STEM_RE = re.compile(r"[^\w\-]")


@dataclass(frozen=True)
class SegmentPlan:
    """Describes one planned segment slice."""

    index: int
    start_sec: float
    duration_sec: float
    output_dir: Path
    output_path: Path


@dataclass
class SplitResult:
    segments: list[Path]
    segment_dirs: list[Path]
    root_dir: Path
    duration_sec: float
    segment_minutes: float


def _safe_stem(name: str, max_len: int = 40) -> str:
    stem = _SAFE_STEM_RE.sub("_", name)[:max_len].strip("_") or "clip"
    return stem


def unique_segment_root(source: Path, base_dir: Path) -> Path:
    """Return a unique root directory for this split job."""
    stem = _safe_stem(Path(source).stem)
    ts = int(time.time())
    return base_dir / f"{stem}_{ts}_segments"


def plan_segments(
    duration_sec: float,
    *,
    segment_minutes: float = DEFAULT_SEGMENT_MINUTES,
) -> list[tuple[float, float]]:
    """Return list of (start_sec, segment_duration_sec) tuples."""
    seg_sec = max(1.0, float(segment_minutes) * 60.0)
    total = max(0.0, float(duration_sec))
    if total <= 0:
        return [(0.0, seg_sec)]
    n = max(1, int(math.ceil(total / seg_sec)))
    plans: list[tuple[float, float]] = []
    for i in range(n):
        start = i * seg_sec
        dur = min(seg_sec, total - start)
        if dur <= 0:
            break
        plans.append((start, dur))
    return plans


def split_video_segments(
    source: Path,
    output_root: Path,
    *,
    segment_minutes: float = DEFAULT_SEGMENT_MINUTES,
    job_id: int | None = None,
) -> SplitResult:
    """Split *source* into fixed-duration segments under *output_root*.

    Each segment lives at ``<output_root>/seg_NNNN/seg_NNNN.mp4``.
    Uses stream-copy (no re-encode) for speed; the ONNX pipeline will re-encode
    each segment during upscale.
    """
    source = Path(source)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    data = probe(source)
    duration_sec = 0.0
    fmt = data.get("format") or {}
    raw = fmt.get("duration")
    if raw not in (None, "N/A", ""):
        try:
            duration_sec = float(raw)
        except (TypeError, ValueError):
            duration_sec = 0.0

    if duration_sec <= 0:
        for stream in data.get("streams") or []:
            raw = stream.get("duration")
            if raw not in (None, "N/A", ""):
                try:
                    duration_sec = float(raw)
                except (TypeError, ValueError):
                    pass
                if duration_sec > 0:
                    break

    if duration_sec <= 0:
        raise RuntimeError(f"Could not determine duration of {source}")

    plans = plan_segments(duration_sec, segment_minutes=segment_minutes)
    segment_paths: list[Path] = []
    segment_dirs: list[Path] = []

    for i, (start, dur) in enumerate(plans):
        seg_name = f"seg_{i:04d}"
        seg_dir = output_root / seg_name
        seg_dir.mkdir(parents=True, exist_ok=True)
        seg_path = seg_dir / f"{seg_name}.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{start:.6f}",
            "-i", str(source),
            "-t", f"{dur:.6f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(seg_path),
        ]
        log.info(
            "Splitting segment %d/%d: %.1f s – %.1f s → %s",
            i + 1, len(plans), start, start + dur, seg_path,
        )
        run_cmd(cmd, job_id=job_id)
        if not seg_path.exists() or seg_path.stat().st_size == 0:
            raise RuntimeError(f"Segment {seg_path} was not created by ffmpeg")
        segment_paths.append(seg_path)
        segment_dirs.append(seg_dir)

    return SplitResult(
        segments=segment_paths,
        segment_dirs=segment_dirs,
        root_dir=output_root,
        duration_sec=duration_sec,
        segment_minutes=segment_minutes,
    )
