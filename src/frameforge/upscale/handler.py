"""Worker handler for upscale stage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.paths import upscaled_dir_for_site
from frameforge.paths_site import site_key_from_job
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.disk import (
    DEFAULT_CHUNK_FRAMES,
    DEFAULT_WARN_DURATION_MINUTES,
    clamp_chunk_frames,
)
from frameforge.upscale.guards import assert_upscale_allowed
from frameforge.upscale.onnx_upscaler import UpscaleConfigError
from frameforge.upscale.pipeline import UpscalePipeline
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


def upscale_output_path_for_job(job: Job, src_path: Path) -> Path:
    dest = upscaled_dir_for_site(site_key_from_job(job))
    dest.mkdir(parents=True, exist_ok=True)
    return dest / f"job{job.id}_{src_path.stem}.upscaled.mp4"


def make_upscale_handler(
    pipeline: UpscalePipeline | None = None,
    *,
    process_registry: ProcessRegistry | None = None,
) -> Callable[[Job, JobRepository], None]:
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
        # Tier 2.2: refuse 4K / ≥2160p with a clear reason (propagates to failed status)
        assert_upscale_allowed(src_path)
        raw_warn = (
            repo.get_setting("upscale_max_duration_min", str(int(DEFAULT_WARN_DURATION_MINUTES)))
            if hasattr(repo, "get_setting")
            else str(int(DEFAULT_WARN_DURATION_MINUTES))
        )
        try:
            warn_min = float(raw_warn)
        except (TypeError, ValueError):
            warn_min = DEFAULT_WARN_DURATION_MINUTES
        pipe.max_duration_minutes = warn_min
        raw_chunk = (
            repo.get_setting("upscale_chunk_frames", str(DEFAULT_CHUNK_FRAMES))
            if hasattr(repo, "get_setting")
            else str(DEFAULT_CHUNK_FRAMES)
        )
        try:
            chunk = int(float(raw_chunk))
        except (TypeError, ValueError):
            chunk = DEFAULT_CHUNK_FRAMES
        pipe.chunk_frames = clamp_chunk_frames(chunk)
        keep = "0"
        if hasattr(repo, "get_setting"):
            keep = str(repo.get_setting("upscale_keep_frames", "0") or "0")
        pipe.keep_frames = keep.strip().lower() in {"1", "true", "yes", "on"}
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
