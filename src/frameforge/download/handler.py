"""Wire yt-dlp downloads into the sequential worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from frameforge.db.repository import Job, JobRepository
from frameforge.download.ytdlp import YtDlpDownloader, apply_gentle_rate
from frameforge.paths import download_dir_for_site, downloads_dir, ensure_output_tree
from frameforge.paths_site import site_key_from_job
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused

log = logging.getLogger(__name__)


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
        force = bool(job.options().get("force_redownload") or job.options().get("ignore_download_archive"))
        dl.ignore_download_archive = force
        if archived is not None and not force:
            path = Path(str(archived["output_path"] or ""))
            if path.is_file():
                title = archived["title"] or job.title
                if title:
                    repo.set_title(job.id, title)
                repo.set_paths(job.id, download_path=str(path), output_path=str(path))
                repo.update_progress(job.id, 100.0)
                repo.clear_live_progress(job.id)
                repo.probe_and_store_resolution(job.id, path)
                from frameforge.download.thumbnails import cache_job_thumbnail

                cache_job_thumbnail(repo, job.id, media_path=path)
                return
            dl.ignore_download_archive = True
            repo.merge_options(
                job.id,
                {"archive_orphan": True, "force_redownload": True, "archive_hit": True},
            )

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
        from frameforge.download.impersonate import require_impersonate_for_url

        require_js_runtime_for_url(job.url)
        require_impersonate_for_url(job.url, repo=repo)

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
        dl.force_impersonate = bool(job.options().get("force_impersonate"))
        dl.use_generic_extractors = bool(job.options().get("use_generic_extractors"))
        from frameforge.download.impersonate import list_impersonate_targets
        from frameforge.download.recovery import (
            BOT_RETRY,
            RETRY,
            SILENT_FIREFOX_COOKIES,
            apply_auto_retry_backoff,
            format_tried,
            next_recovery_step,
            recovery_should_abort,
            silent_cookie_import,
            silent_cookies_enabled,
        )
        from frameforge.errors import classify_error

        attempts: list[str] = list(job.options().get("recovery_attempts") or [])
        last_exc: BaseException | None = None
        result = None

        def _raise_if_backoff_aborted() -> None:
            reason = recovery_should_abort(job.id, repo, process_registry)
            if reason == "paused":
                raise DownloadPaused("paused")
            raise DownloadCancelled("cancelled")
        while True:
            try:
                result = dl.download(
                    job.url,
                    progress_cb=progress_cb,
                    job_id=job.id,
                    process_registry=process_registry,
                )
                last_exc = None
                break
            except (DownloadCancelled, DownloadPaused):
                raise
            except Exception as exc:
                last_exc = exc
                if bool(getattr(dl, "aria2_fallback_native", False)) and "native" not in attempts:
                    attempts.append("native")
                inv = getattr(dl, "last_invocation", None) or {}
                if inv.get("impersonate") and "impersonate" not in attempts:
                    attempts.append("impersonate")
                cat = classify_error(str(exc), url=job.url)
                impersonated = bool(inv.get("impersonate")) or bool(dl.force_impersonate)
                step = next_recovery_step(
                    attempts,
                    category=cat,
                    message=str(exc),
                    url=job.url,
                    impersonated=impersonated,
                    has_impersonate_targets=bool(list_impersonate_targets()),
                    silent_cookies=silent_cookies_enabled(repo),
                )
                if step is None:
                    break
                if step == "impersonate":
                    dl.force_impersonate = True
                    attempts.append("impersonate")
                    if progress_cb:
                        progress_cb(
                            0.0,
                            {
                                "speed_bps": None,
                                "eta_seconds": None,
                                "speed_str": "Retrying with browser impersonate…",
                                "eta_str": None,
                            },
                        )
                    continue
                if step == SILENT_FIREFOX_COOKIES or step == "cookies":
                    attempts.append(SILENT_FIREFOX_COOKIES)
                    repo.merge_options(
                        job.id,
                        {
                            "recovery_attempts": attempts,
                            "recovery_tried": format_tried(attempts),
                        },
                    )
                    if progress_cb:
                        progress_cb(
                            0.0,
                            {
                                "speed_bps": None,
                                "eta_seconds": None,
                                "speed_str": "Importing cookies from Firefox…",
                                "eta_str": None,
                            },
                        )
                    try:
                        imported = silent_cookie_import(job.url)
                    except Exception as rec_exc:  # noqa: BLE001
                        log.exception("silent cookie import crashed for job %s", job.id)
                        imported = {
                            "ok": False,
                            "stage": "error",
                            "message": f"cookie recovery error: {rec_exc}",
                        }
                    if imported.get("ok"):
                        from frameforge.download.cookie_validate import mark_cookies_validated

                        mark_cookies_validated(job.url)
                        dl.cookiefile = _cookiefile_for_url(job.url)
                        browser = str(imported.get("browser") or "firefox").strip() or "firefox"
                        if imported.get("skipped_import"):
                            toast = "Using existing cookies — retrying…"
                        else:
                            toast = f"Cookies refreshed ({browser.capitalize()}) — retrying…"
                        repo.merge_options(job.id, {"recovery_toast": toast})
                        if progress_cb:
                            progress_cb(
                                0.0,
                                {
                                    "speed_bps": None,
                                    "eta_seconds": None,
                                    "speed_str": "Cookies validated — waiting before retry…",
                                    "eta_str": None,
                                },
                            )
                        try:
                            backoff_ok = apply_auto_retry_backoff(
                                repo=repo,
                                attempts=attempts,
                                job_id=job.id,
                                progress_cb=progress_cb,
                                process_registry=process_registry,
                            )
                        except Exception:  # noqa: BLE001
                            log.exception("auto-retry backoff crashed for job %s", job.id)
                            break
                        if not backoff_ok:
                            _raise_if_backoff_aborted()
                        if RETRY not in attempts:
                            attempts.append(RETRY)
                        repo.merge_options(
                            job.id,
                            {
                                "recovery_attempts": attempts,
                                "recovery_tried": format_tried(attempts),
                            },
                        )
                        if progress_cb:
                            progress_cb(
                                0.0,
                                {
                                    "speed_bps": None,
                                    "eta_seconds": None,
                                    "speed_str": "Retrying download…",
                                    "eta_str": None,
                                },
                            )
                        continue
                    step = next_recovery_step(
                        attempts,
                        category=cat,
                        message=str(exc),
                        url=job.url,
                        impersonated=bool(dl.force_impersonate) or impersonated,
                        has_impersonate_targets=bool(list_impersonate_targets()),
                        silent_cookies=False,
                    )
                if step == BOT_RETRY:
                    attempts.append(BOT_RETRY)
                    repo.merge_options(
                        job.id,
                        {
                            "recovery_attempts": attempts,
                            "recovery_tried": format_tried(attempts),
                        },
                    )
                    if not apply_auto_retry_backoff(
                        repo=repo,
                        attempts=attempts,
                        job_id=job.id,
                        progress_cb=progress_cb,
                        process_registry=process_registry,
                    ):
                        _raise_if_backoff_aborted()
                    if progress_cb:
                        progress_cb(
                            0.0,
                            {
                                "speed_bps": None,
                                "eta_seconds": None,
                                "speed_str": "Retrying after backoff…",
                                "eta_str": None,
                            },
                        )
                    continue
                if step == "generic":
                    dl.use_generic_extractors = True
                    attempts.append("generic")
                    if progress_cb:
                        progress_cb(
                            0.0,
                            {
                                "speed_bps": None,
                                "eta_seconds": None,
                                "speed_str": "Retrying with generic extractor…",
                                "eta_str": None,
                            },
                        )
                    continue
                break
        inv = getattr(dl, "last_invocation", None)
        if not inv and hasattr(dl, "describe_cli_invocation"):
            try:
                inv = dl.describe_cli_invocation(job.url)
            except Exception:  # noqa: BLE001
                inv = None
        extra: dict[str, Any] = {
            "recovery_attempts": attempts,
            "recovery_tried": format_tried(attempts),
            "force_impersonate": bool(dl.force_impersonate),
            "use_generic_extractors": bool(dl.use_generic_extractors),
        }
        if inv:
            extra.update(
                {
                    "ytdlp_invocation": inv,
                    "download_method": getattr(dl, "download_method", None)
                    or ("native" if not dl._aria2c_enabled() else "aria2c"),
                    "aria2_fallback_native": bool(getattr(dl, "aria2_fallback_native", False)),
                    "download_attempt": int(getattr(dl, "download_attempt", 1) or 1),
                    "resolved_path": inv.get("resolved_path"),
                    "recovery_method": inv.get("recovery_method"),
                    "archive_hit": bool(inv.get("archive_hit")),
                }
            )
        repo.merge_options(job.id, extra)
        if last_exc is not None:
            raise last_exc
        if result is None:
            raise RuntimeError("Download failed with no result")
        # If cancelled mid-flight after process death, do not mark success
        if repo.get(job.id).status == "cancelled":
            raise DownloadCancelled("cancelled")
        if repo.get(job.id).status == "paused":
            raise DownloadPaused("paused")
        repo.set_title(job.id, result.title)
        from frameforge.download.metadata import display_extractor

        ext_key = result.info.get("extractor_key") or result.info.get("extractor")
        if ext_key:
            repo.set_extractor(job.id, display_extractor(str(ext_key), job.url))
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
