"""Pure view-models for queue/history cards (no Flet). Tests and UI share this."""

from __future__ import annotations

from typing import Any

from frameforge.errors import human_cause
from frameforge.gui.actions import can_convert, can_download, can_upscale

STATUS_PILL = {
    "pending": "Queued",
    "downloading": "Downloading",
    "upscaling": "Upscaling",
    "converting": "Converting",
    "convert_pending": "Convert queued",
    "download_completed": "Downloaded",
    "completed": "Completed",
    "failed": "Failed",
    "paused": "Paused",
    "cancelled": "Cancelled",
}

OVERFLOW_IDS = (
    "retry",
    "upscale",
    "convert",
    "set_format",
    "open_folder",
    "reveal_file",
    "remove_from_queue",
)


def status_pill(job: Any) -> str:
    if getattr(job, "upscale_blocked", False):
        return "BLOCKED 4K+"
    return STATUS_PILL.get(getattr(job, "status", ""), str(getattr(job, "status", "")).title())


def resolution_label(job: Any) -> str | None:
    w, h = getattr(job, "source_width", None), getattr(job, "source_height", None)
    if h:
        if w:
            return f"{w}x{h}"
        return f"{h}p"
    return None


def card_view(
    job: Any,
    *,
    selected: bool = False,
    expanded: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    opts = job.options() if hasattr(job, "options") else {}
    cause = opts.get("error_cause") or (
        human_cause(opts["error_category"]) if opts.get("error_category") else None
    )
    return {
        "id": job.id,
        "title": job.title or job.url,
        "url": job.url,
        "domain": getattr(job, "site_key", None) or "",
        "status": status_pill(job),
        "raw_status": job.status,
        "selected": selected,
        "progress": float(job.progress) if show_progress else None,
        "failed": job.status == "failed",
        "expanded": expanded and job.status == "failed",
        "cause": cause or (job.error or ""),
        "error": job.error or "",
        "recommended": bool(getattr(job, "upscale_recommended", False) and job.status == "completed"),
        "blocked_4k": bool(getattr(job, "upscale_blocked", False)),
        "can_upscale": can_upscale(job) and not getattr(job, "upscale_blocked", False),
        "can_convert": can_convert(job),
        "can_download": can_download(job),
        "resolution": resolution_label(job),
        "thumbnail_path": getattr(job, "thumbnail_path", None),
    }


def overflow_actions(job: Any) -> list[str]:
    actions = ["set_format", "open_folder", "reveal_file", "remove_from_queue"]
    if job.status == "failed":
        actions.insert(0, "retry")
    if can_upscale(job) and not getattr(job, "upscale_blocked", False):
        actions.insert(0, "upscale")
    if can_convert(job):
        actions.insert(1 if "upscale" in actions else 0, "convert")
    return actions


def floating_bar_view(jobs: list[Any], selected_ids: set[int]) -> dict[str, Any] | None:
    if not selected_ids:
        return None
    selected = [j for j in jobs if j.id in selected_ids]
    if not selected:
        return None
    return {
        "count": len(selected),
        "show_download": any(can_download(j) for j in selected),
        "show_upscale": any(can_upscale(j) and not getattr(j, "upscale_blocked", False) for j in selected),
        "show_convert": any(can_convert(j) for j in selected),
        "ids": [j.id for j in selected],
    }


def structural_sig(jobs: list[Any]) -> tuple[Any, ...]:
    """Identity of the list (not live progress) — progress ticks must not rebuild."""
    return tuple((j.id, j.status, j.title) for j in jobs)
