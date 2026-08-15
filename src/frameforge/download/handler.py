"""Wire yt-dlp downloads into the sequential worker."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from frameforge.db.repository import Job, JobRepository
from frameforge.download.ytdlp import YtDlpDownloader, apply_gentle_rate
from frameforge.paths import download_dir_for_site, downloads_dir, ensure_output_tree
from frameforge.paths_site import site_key_from_job
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


def resolve_download_output_dir(job: Job, *, fallback: Path | None = None) -> Path:
    """Site folder for new jobs; keep resume paths and explicit non-default output dirs."""
    opts = job.options()
    existing = opts.get("download_output_dir")
    if existing:
        dest = Path(existing)
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    if fallback is not None:
        try:
            if fallback.resolve() != downloads_dir().resolve():
                fallback.mkdir(parents=True, exist_ok=True)
                return fallback
        except OSError:
            pass
    dest = download_dir_for_site(site_key_from_job(job))
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _cookiefile_for_url(url: str) -> Path | None:
    from frameforge.download.cookies import resolve_cookiefile_for_url

    return resolve_cookiefile_for_url(url)


def make_download_handler(
    downloader: YtDlpDownloader | None = None,
    *,
    process_registry: ProcessRegistry | None = None,
) -> Callable[[Job, JobRepository], None]:
    ensure_output_tree()
    dl = downloader or YtDlpDownloader()

    def handler(job: Job, repo: JobRepository) -> None:
        job = repo.get(job.id)
        if job.status == "cancelled":
            raise DownloadCancelled("cancelled")
        if job.status == "paused":
            raise DownloadPaused("paused")
        if process_registry is not None and process_registry.was_killed(job.id):
            raise DownloadCancelled("cancelled")
        if process_registry is not None and process_registry.was_paused(job.id):
            raise DownloadPaused("paused")

        out_dir = resolve_download_output_dir(job, fallback=dl.output_dir)
        dl.output_dir = out_dir
        repo.merge_options(
            job.id,
            {
                "download_output_dir": str(out_dir),
                "site_key": site_key_from_job(job),
            },
        )

        archived = repo.archive_lookup(job.url)
        if archived is not None:
            path = archived["output_path"]
            title = archived["title"] or job.title
            if title:
                repo.set_title(job.id, title)
            repo.set_paths(job.id, download_path=path, output_path=path)
            repo.update_progress(job.id, 100.0)
            repo.clear_live_progress(job.id)
            repo.probe_and_store_resolution(job.id, path)
            from frameforge.download.thumbnails import cache_job_thumbnail

            cache_job_thumbnail(repo, job.id, media_path=path)
            return

        def progress_cb(pct: float, meta: dict[str, Any] | None = None) -> None:
            current = repo.get(job.id)
            if current.status == "cancelled":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadCancelled("cancelled")
            if current.status == "paused":
                if process_registry is not None:
                    process_registry.kill(job.id)
                raise DownloadPaused("paused")
            meta = meta or {}
            repo.update_progress(
                job.id,
                pct,
                speed_bps=meta.get("speed_bps"),
                eta_seconds=meta.get("eta_seconds"),
                speed_str=meta.get("speed_str"),
                eta_str=meta.get("eta_str"),
            )

        from frameforge.download.js_runtime import require_js_runtime_for_url

        require_js_runtime_for_url(job.url)

        dl.format_preference = job.format_preference or "best"
        from frameforge.download.cookie_validate import consume_gentle_job

        apply_gentle_rate(dl, consume_gentle_job(repo))
        if not dl.limit_rate_bps:
            from frameforge.download.throughput import max_download_rate_bps

            cap = max_download_rate_bps(repo)
            if cap:
                dl.limit_rate_bps = cap
        dl.cookiefile = _cookiefile_for_url(job.url)
        from frameforge.download.youtube_clients import innertube_enabled

        dl._settings_repo = repo
        dl.youtube_innertube = innertube_enabled(repo)
        try:
            result = dl.download(
                job.url,
                progress_cb=progress_cb,
                job_id=job.id,
                process_registry=process_registry,
            )
        finally:
            inv = getattr(dl, "last_invocation", None)
            if not inv and hasattr(dl, "describe_cli_invocation"):
                try:
                    inv = dl.describe_cli_invocation(job.url)
                except Exception:  # noqa: BLE001
                    inv = None
            if inv:
                repo.merge_options(
                    job.id,
                    {
                        "ytdlp_invocation": inv,
                        "download_method": getattr(dl, "download_method", None)
                        or ("native" if not dl._aria2c_enabled() else "aria2c"),
                        "aria2_fallback_native": bool(getattr(dl, "aria2_fallback_native", False)),
                        "download_attempt": int(getattr(dl, "download_attempt", 1) or 1),
                    },
                )
        # If cancelled mid-flight after process death, do not mark success
        if repo.get(job.id).status == "cancelled":
            raise DownloadCancelled("cancelled")
        if repo.get(job.id).status == "paused":
            raise DownloadPaused("paused")
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
        repo.probe_and_store_resolution(job.id, result.path)
        from frameforge.download.thumbnails import cache_job_thumbnail

        cache_job_thumbnail(repo, job.id, info=result.info, media_path=result.path)

    return handler
