"""Wire yt-dlp downloads into the sequential worker."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from frameforge.db.repository import Job, JobRepository
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree


def _cookiefile_for_url(url: str) -> Path | None:
    from frameforge.download.cookies import resolve_cookiefile_for_url

    return resolve_cookiefile_for_url(url)


def make_download_handler(
    downloader: YtDlpDownloader | None = None,
) -> Callable[[Job, JobRepository], None]:
    ensure_output_tree()
    dl = downloader or YtDlpDownloader()

    def handler(job: Job, repo: JobRepository) -> None:
        job = repo.get(job.id)
        if job.status == "cancelled":
            return

        archived = repo.archive_lookup(job.url)
        if archived is not None:
            path = archived["output_path"]
            title = archived["title"] or job.title
            if title:
                repo.set_title(job.id, title)
            repo.set_paths(job.id, download_path=path, output_path=path)
            repo.update_progress(job.id, 100.0)
            repo.clear_live_progress(job.id)
            return

        def progress_cb(pct: float, meta: dict[str, Any] | None = None) -> None:
            current = repo.get(job.id)
            if current.status == "cancelled":
                raise RuntimeError("cancelled")
            meta = meta or {}
            repo.update_progress(
                job.id,
                pct,
                speed_bps=meta.get("speed_bps"),
                eta_seconds=meta.get("eta_seconds"),
                speed_str=meta.get("speed_str"),
                eta_str=meta.get("eta_str"),
            )

        dl.format_preference = job.format_preference or "best"
        cookie = _cookiefile_for_url(job.url)
        if cookie is not None:
            dl.cookiefile = cookie
        result = dl.download(job.url, progress_cb=progress_cb)
        repo.set_title(job.id, result.title)
        repo.set_paths(job.id, download_path=str(result.path), output_path=str(result.path))
        repo.add_archive(
            job.url,
            title=result.title,
            output_path=str(result.path),
            extractor_key=str(result.info.get("extractor_key") or result.info.get("extractor")),
            video_id=str(result.info.get("id")) if result.info.get("id") else None,
        )
        repo.update_progress(job.id, 100.0)
        repo.clear_live_progress(job.id)

    return handler
