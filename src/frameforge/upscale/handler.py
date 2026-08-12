"""Worker handler for upscale stage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.paths import upscaled_dir
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.guards import assert_upscale_allowed
from frameforge.upscale.pipeline import UpscalePipeline
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


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
        # Tier 2.2: refuse 4K / ≥2160p with a clear reason (propagates to failed status)
        assert_upscale_allowed(src_path)
        out = upscaled_dir() / f"job{job.id}_{src_path.stem}.upscaled.mp4"

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
