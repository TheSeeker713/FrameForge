"""Copyable full error reports for fail-pause, auth, and job cards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from frameforge import __version__
from frameforge.download.invocation import argv_summary
from frameforge.download.recovery import format_tried
from frameforge.errors import classify_error, format_error_panel, human_cause


def format_full_error_report(
    job: Any | None = None,
    *,
    payload: dict[str, Any] | None = None,
    extra_error: str | None = None,
    app_version: str | None = None,
) -> str:
    """Plain-text report: timestamp, job, URL, category, cause, stderr, argv, version."""
    payload = payload or {}
    opts: dict[str, Any] = {}
    if job is not None and hasattr(job, "options"):
        opts = job.options() or {}
    inv = opts.get("ytdlp_invocation") if isinstance(opts.get("ytdlp_invocation"), dict) else {}
    job_id = payload.get("job_id")
    if job_id is None:
        job_id = getattr(job, "id", None)
    url = payload.get("url") or getattr(job, "url", None) or ""
    cat = payload.get("category") or opts.get("error_category")
    if not cat and job is not None:
        cat = classify_error(
            getattr(job, "error", None),
            status=getattr(job, "status", None),
            url=url or getattr(job, "url", None),
        )
    cause = payload.get("cause") or opts.get("error_cause") or (human_cause(cat) if cat else "")
    err = extra_error or payload.get("error") or getattr(job, "error", None) or ""
    stderr = opts.get("error_stderr_tail") or ""
    argv = inv.get("argv") if inv else None
    lines = [
        "FrameForge error report",
        f"timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"app_version: {app_version or __version__}",
        f"job_id: {job_id if job_id is not None else ''}",
        f"url: {url}",
        f"category: {cat or ''}",
        f"cause: {cause}",
        f"tried: {payload.get('tried') or opts.get('recovery_tried') or format_tried(opts.get('recovery_attempts')) or '(none)'}",
        "error:",
        str(err).strip() or "(empty)",
        "stderr_tail:",
        str(stderr).strip() or "(empty)",
        f"argv: {argv_summary(list(argv)) if argv else '(none)'}",
    ]
    if inv:
        lines.append(f"cwd: {inv.get('cwd') or ''}")
        lines.append(f"cookies: {inv.get('cookies') or '(none)'}")
        lines.append(f"cookies_attached: {inv.get('cookies_attached', bool(inv.get('cookies')))}")
        lines.append(f"concurrent_fragments: {inv.get('concurrent_fragments', '')}")
        lines.append(f"throttled_rate: {inv.get('throttled_rate') or ''}")
        lines.append(f"http_chunk_size: {inv.get('http_chunk_size') or ''}")
        lines.append(f"aria2c: {inv.get('aria2c')}")
        if inv.get("aria2_args"):
            lines.append(f"aria2_args: {inv.get('aria2_args')}")
        lines.append(f"player_client: {inv.get('player_client') or '(none)'}")
        lines.append(f"impersonate: {inv.get('impersonate') or '(none)'}")
        lines.append(f"use_extractors: {inv.get('use_extractors') or '(default)'}")
        lines.append(f"format: {inv.get('format') or ''}")
        lines.append(f"ffmpeg_location: {inv.get('ffmpeg_location') or '(not found)'}")
        if inv.get("ffprobe_location"):
            lines.append(f"ffprobe_location: {inv.get('ffprobe_location')}")
        lines.append(f"yt_dlp_version: {inv.get('yt_dlp_version') or ''}")
        runtime = inv.get("js_runtime") or (inv.get("env_overrides") or {}).get("js_runtime")
        lines.append(f"js_runtime: {runtime or '(none — Deno/Node not detected)'}")
        if inv.get("js_runtimes"):
            lines.append(f"js_runtimes: {inv.get('js_runtimes')}")
        if not runtime:
            from frameforge.download.js_runtime import JS_RUNTIME_FIX

            lines.append(f"js_runtime_fix: {JS_RUNTIME_FIX}")
        if inv.get("returncode") is not None:
            lines.append(f"returncode: {inv.get('returncode')}")
        if inv.get("stderr_empty"):
            lines.append("note: no stderr; see invocation log")
    if opts.get("disk_estimated_bytes") is not None:
        lines.append(f"disk_estimated_bytes: {opts.get('disk_estimated_bytes')}")
        lines.append(f"disk_required_bytes: {opts.get('disk_required_bytes')}")
        lines.append(f"disk_free_bytes: {opts.get('disk_free_bytes')}")
        if opts.get("disk_volume"):
            lines.append(f"disk_volume: {opts.get('disk_volume')}")
    if job is not None:
        panel = format_error_panel(job)
        if panel and panel not in "\n".join(lines):
            lines.extend(["", "error_panel:", panel])
    text = "\n".join(str(x) for x in lines).strip()
    return text + "\n"
