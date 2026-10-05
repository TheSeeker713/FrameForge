"""Worker handler for upscale stage."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.paths import upscaled_dir_for_site, temp_dir
from frameforge.paths_site import site_key_from_job
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.disk import (
    DEFAULT_CHUNK_FRAMES,
    DEFAULT_WARN_DURATION_MINUTES,
    clamp_chunk_frames,
    video_metrics,
)
from frameforge.upscale.estimate import (
    FOUR_HOUR_GATE_SECONDS,
    UpscaleEstimate,
    estimate_upscale,
)
from frameforge.upscale.guards import assert_upscale_allowed
from frameforge.upscale.onnx_upscaler import UpscaleConfigError, model_status
from frameforge.upscale.pipeline import UpscalePipeline
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused

log = logging.getLogger(__name__)


class UpscaleGateError(RuntimeError):
    """Raised when the 4-hour gate blocks a full-file upscale.

    The caller should present the onboarding dialog or segment-split option
    rather than letting this propagate to a generic failure.
    """

    category = "upscale_gate"

    def __init__(self, estimate: UpscaleEstimate, source_name: str = "") -> None:
        self.estimate = estimate
        self.source_name = source_name
        super().__init__(
            f"Upscale gate: {source_name!r} estimated {estimate.label} "
            f"(>{FOUR_HOUR_GATE_SECONDS / 3600:.0f} h). "
            "Use split-into-segments workflow to proceed."
        )

    def option_patch(self) -> dict:
        return {
            "upscale_gate_total_seconds": self.estimate.total_seconds,
            "upscale_gate_fps_estimate": self.estimate.fps_estimate,
            "upscale_gate_total_frames": self.estimate.total_frames,
            "upscale_gate_label": self.estimate.label,
        }


def _read_chunk_settings(repo: JobRepository | None) -> tuple[int, float, bool]:
    """Return (chunk_frames, warn_min, keep_frames) from repo settings."""
    if repo is None or not hasattr(repo, "get_setting"):
        return DEFAULT_CHUNK_FRAMES, DEFAULT_WARN_DURATION_MINUTES, False

    raw_warn = str(
        repo.get_setting("upscale_max_duration_min", str(int(DEFAULT_WARN_DURATION_MINUTES))) or ""
    )
    try:
        warn_min = float(raw_warn)
    except (TypeError, ValueError):
        warn_min = DEFAULT_WARN_DURATION_MINUTES

    raw_chunk = str(repo.get_setting("upscale_chunk_frames", str(DEFAULT_CHUNK_FRAMES)) or "")
    try:
        chunk = clamp_chunk_frames(int(float(raw_chunk)))
    except (TypeError, ValueError):
        chunk = DEFAULT_CHUNK_FRAMES

    keep = str(repo.get_setting("upscale_keep_frames", "0") or "0")
    keep_frames = keep.strip().lower() in {"1", "true", "yes", "on"}

    return chunk, warn_min, keep_frames


def _estimate_for_source(
    src_path: Path,
    pipe: UpscalePipeline,
    chunk: int,
) -> UpscaleEstimate:
    """Build a time estimate (probe then fallback) for *src_path*."""
    metrics = video_metrics(src_path)
    cached: float | None = None
    # A stored fps hint can be provided via job options; fall through to probe/fallback.
    return estimate_upscale(
        metrics,
        chunk_frames=chunk,
        model_path=pipe.upscaler.model_path,
        tile=pipe._tile,
        cached_fps=cached,
        run_probe=False,  # probe is expensive; use fallback table by default
    )


def upscale_output_path_for_job(job: Job, src_path: Path) -> Path:
    dest = upscaled_dir_for_site(site_key_from_job(job))
    dest.mkdir(parents=True, exist_ok=True)
    return dest / f"job{job.id}_{src_path.stem}.upscaled.mp4"


def make_upscale_handler(
    pipeline: UpscalePipeline | None = None,
    *,
    process_registry: ProcessRegistry | None = None,
    enforce_gate: bool = True,
) -> Callable[[Job, JobRepository], None]:
    """Return a handler for the 'upscaling' queue stage.

    Parameters
    ----------
    enforce_gate:
        When True (default), raise ``UpscaleGateError`` when the estimated
        completion time exceeds 4 hours.  Set to False to skip the gate check
        (e.g. when processing individual segments after a split).
    """
    pipe = pipeline or UpscalePipeline()

    def handler(job: Job, repo: JobRepository) -> None:
        job = repo.get(job.id)
        src = job.download_path or job.output_path
        if not src or not Path(src).exists():
            raise FileNotFoundError(f"No download artifact for job {job.id}")
        src_path = Path(src)
        if not pipe.upscale_available:
            from frameforge.upscale.bootstrap import maybe_create_smoke_onnx

            maybe_create_smoke_onnx()
            pipe.reload_model()
        if not pipe.upscale_available:
            raise UpscaleConfigError(pipe.upscale_unavailable_reason)

        # ≥2160p is blocked unconditionally.
        assert_upscale_allowed(src_path)

        chunk, warn_min, keep_frames = _read_chunk_settings(repo)
        pipe.max_duration_minutes = warn_min
        pipe.chunk_frames = chunk
        pipe.keep_frames = keep_frames

        # 4-hour gate: refuse full-file upscale if estimate exceeds threshold.
        if enforce_gate:
            est = _estimate_for_source(src_path, pipe, chunk)
            if est.exceeds_gate:
                raise UpscaleGateError(est, src_path.name)

        out = upscale_output_path_for_job(job, src_path)

        def progress_cb(pct: float) -> None:
            if repo.get(job.id).status == "cancelled":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadCancelled("cancelled")
            if repo.get(job.id).status == "paused":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadPaused("paused")
            repo.update_progress(job.id, pct)

        def should_stop() -> bool:
            return repo.get(job.id).status in ("cancelled", "paused")

        result = pipe.run(
            src_path,
            job_key=f"job_{job.id}",
            output_path=out,
            progress_cb=progress_cb,
            should_stop=should_stop,
            job_id=job.id,
            process_registry=process_registry,
        )
        if repo.get(job.id).status == "cancelled":
            raise DownloadCancelled("cancelled")
        if repo.get(job.id).status == "paused":
            raise DownloadPaused("paused")
        repo.set_paths(job.id, output_path=str(result.output_path))
        repo.update_progress(job.id, 100.0)

    return handler


def make_segment_upscale_handler(
    pipeline: UpscalePipeline | None = None,
    *,
    process_registry: ProcessRegistry | None = None,
) -> Callable[[Job, JobRepository], None]:
    """Handler for upscaling individual 15-min segments (gate disabled)."""
    return make_upscale_handler(
        pipeline,
        process_registry=process_registry,
        enforce_gate=False,
    )


def plan_and_split_source(
    src_path: Path,
    *,
    segment_minutes: float = 15.0,
    job_id: int | None = None,
) -> "SplitResult":  # noqa: F821 – avoid circular import at module level
    """Split *src_path* into ~segment_minutes segments under a unique temp dir.

    Returns the ``SplitResult`` with all segment paths ready for enqueueing.
    """
    from frameforge.upscale.segment_split import SplitResult, split_video_segments, unique_segment_root

    root = unique_segment_root(src_path, temp_dir())
    return split_video_segments(
        src_path,
        root,
        segment_minutes=segment_minutes,
        job_id=job_id,
    )
