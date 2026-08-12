"""Worker handler for upscale stage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.paths import upscaled_dir
from frameforge.upscale.pipeline import UpscalePipeline


def make_upscale_handler(
    pipeline: UpscalePipeline | None = None,
) -> Callable[[Job, JobRepository], None]:
    pipe = pipeline or UpscalePipeline(max_frames=30)

    def handler(job: Job, repo: JobRepository) -> None:
        job = repo.get(job.id)
        src = job.download_path or job.output_path
        if not src or not Path(src).exists():
            raise FileNotFoundError(f"No download artifact for job {job.id}")
        out = upscaled_dir() / f"job{job.id}_{Path(src).stem}.upscaled.mp4"

        def progress_cb(pct: float) -> None:
            if repo.get(job.id).status == "cancelled":
                raise RuntimeError("cancelled")
            repo.update_progress(job.id, pct)

        def should_stop() -> bool:
            return repo.get(job.id).status == "cancelled"

        result = pipe.run(
            Path(src),
            job_key=f"job_{job.id}",
            output_path=out,
            progress_cb=progress_cb,
            should_stop=should_stop,
        )
        repo.set_paths(job.id, output_path=str(result.output_path))
        repo.update_progress(job.id, 100.0)

    return handler
