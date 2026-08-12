"""Worker handler for convert-to-MP3 stage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from frameforge.convert.mp3 import convert_to_mp3
from frameforge.db.repository import Job, JobRepository
from frameforge.paths import converted_dir_for_site
from frameforge.paths_site import site_key_from_job
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


def local_media_path(job: Job) -> Path | None:
    for raw in (job.output_path, job.download_path):
        if raw and Path(raw).is_file():
            return Path(raw)
    return None


def convert_output_path_for_job(job: Job, src: Path) -> Path:
    dest = converted_dir_for_site(site_key_from_job(job))
    dest.mkdir(parents=True, exist_ok=True)
    return dest / f"job{job.id}_{src.stem}.mp3"


def make_convert_handler(
    *,
    process_registry: ProcessRegistry | None = None,
) -> Callable[[Job, JobRepository], None]:
    def handler(job: Job, repo: JobRepository) -> None:
        job = repo.get(job.id)
        src = local_media_path(job)
        if src is None:
            raise FileNotFoundError(f"ffmpeg: input not found for job {job.id}")
        out = convert_output_path_for_job(job, src)

        def progress_cb(pct: float) -> None:
            current = repo.get(job.id)
            if current.status == "cancelled":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadCancelled("cancelled")
            if current.status == "paused":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadPaused("paused")
            repo.update_progress(job.id, pct)

        result = convert_to_mp3(
            src,
            out,
            job_id=job.id,
            process_registry=process_registry,
            progress_cb=progress_cb,
        )
        if repo.get(job.id).status == "cancelled":
            raise DownloadCancelled("cancelled")
        if repo.get(job.id).status == "paused":
            raise DownloadPaused("paused")
        repo.merge_options(job.id, {"convert_path": str(result)})
        repo.update_progress(job.id, 100.0)

    return handler
