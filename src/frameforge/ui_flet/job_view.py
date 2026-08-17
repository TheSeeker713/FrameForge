"""Pure view-models for queue/history cards (no Flet). Tests and UI share this."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from frameforge.errors import human_cause
from frameforge.errors import AUTH_REQUIRED, BOT_CHECK, IMPERSONATION_MISSING
from frameforge.gui.actions import can_convert, can_download, can_retry_download, can_upscale

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

ACTIVE_CARD_STATUSES = frozenset({"downloading", "upscaling", "converting"})

OVERFLOW_IDS = (
    "retry",
    "upscale",
    "convert",
    "set_format",
    "open_folder",
    "reveal_file",
    "remove_from_queue",
)

MORE_LABELS = {
    "download_selected": "Download selected",
    "upscale": "Upscale 2x",
    "convert": "Convert to MP3",
    "set_format": "Set format",
    "clear_selected": "Clear selected",
    "retry_selected": "Retry / Resume selected",
    "open_folder": "Open folder",
    "reveal_file": "Reveal file",
    "select_recommended": "Select recommended",
    "clear_finished": "Clear finished",
    "download_all": "Download all pending",
    "retry": "Retry",
    "remove_from_queue": "Clear from queue",
}

OVERFLOW_LABELS = {
    "retry": "Retry / Resume download",
    "upscale": "Upscale 2x",
    "convert": "Convert to MP3",
    "set_format": "Set format",
    "open_folder": "Open folder",
    "reveal_file": "Reveal file",
    "remove_from_queue": "Clear from queue",
}


def status_pill(job: Any) -> str:
    if getattr(job, "upscale_blocked", False):
        return "BLOCKED 4K+"
    return STATUS_PILL.get(getattr(job, "status", ""), str(getattr(job, "status", "")).title())


def extractor_badge(job: Any) -> str:
    """Site folder or `[generic]` when yt-dlp used the generic extractor."""
    from frameforge.download.metadata import display_extractor

    ext = display_extractor(getattr(job, "extractor", None), getattr(job, "url", None))
    if ext == "generic":
        return "[generic]"
    return getattr(job, "site_key", None) or ext or ""


def fail_action_ids(category: str | None) -> list[str]:
    """Non-auth failures (ffmpeg, aria2_forbidden, js_runtime, network) lead with Retry."""
    if category in (AUTH_REQUIRED, BOT_CHECK, IMPERSONATION_MISSING):
        return ["reauth", "retry", "copy"]
    return ["retry", "copy"]


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
    active = job.status in ACTIVE_CARD_STATUSES
    show_bar = bool(show_progress or active)
    progress_val = float(getattr(job, "progress", 0) or 0) if show_bar else None
    return {
        "id": job.id,
        "title": job.title or job.url,
        "url": job.url,
        "domain": extractor_badge(job),
        "status": status_pill(job),
        "raw_status": job.status,
        "selected": selected,
        "progress": progress_val,
        "speed": opts.get("speed_str") or "",
        "eta": opts.get("eta_str") or "",
        "failed": job.status == "failed",
        "expanded": expanded and job.status == "failed",
        "cause": cause or (job.error or ""),
        "error": job.error or "",
        "recommended": bool(getattr(job, "upscale_recommended", False) and job.status == "completed"),
        "blocked_4k": bool(getattr(job, "upscale_blocked", False)),
        "blocked_4k_hint": (
            "Upscale blocked (≥2160p); download may still be completed"
            if getattr(job, "upscale_blocked", False)
            else ""
        ),
        "can_upscale": can_upscale(job) and not getattr(job, "upscale_blocked", False),
        "can_convert": can_convert(job),
        "can_download": can_download(job),
        "resolution": resolution_label(job),
        "thumbnail_path": getattr(job, "thumbnail_path", None),
        "active": active,
        "error_category": opts.get("error_category") or "",
    }


def overflow_actions(job: Any) -> list[str]:
    actions = ["set_format", "open_folder", "reveal_file", "remove_from_queue"]
    if can_retry_download(job):
        actions.insert(0, "retry")
    if can_upscale(job) and not getattr(job, "upscale_blocked", False):
        actions.insert(0, "upscale")
    if can_convert(job):
        actions.insert(1 if "upscale" in actions else 0, "convert")
    return actions


def _has_local_file(job: Any) -> bool:
    for raw in (getattr(job, "output_path", None), getattr(job, "download_path", None)):
        if raw and Path(raw).exists():
            return True
    return False


def more_menu_items(jobs: list[Any], selected_ids: set[int]) -> list[str]:
    """Action ids for the More menu. Empty handlers are forbidden — every id is wired."""
    selected = [j for j in jobs if j.id in selected_ids]
    items: list[str] = []
    if any(can_download(j) for j in selected):
        items.append("download_selected")
    if any(can_upscale(j) and not getattr(j, "upscale_blocked", False) for j in selected):
        items.append("upscale")
    if any(can_convert(j) for j in selected):
        items.append("convert")
    items.append("set_format")
    items.append("clear_selected")
    if any(can_retry_download(j) for j in selected):
        items.append("retry_selected")
    if len(selected) == 1 and _has_local_file(selected[0]):
        items.append("open_folder")
        items.append("reveal_file")
    items.append("select_recommended")
    items.append("clear_finished")
    return items


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
        "show_clear": True,
        "show_retry": any(can_retry_download(j) for j in selected),
        "ids": [j.id for j in selected],
        "more_items": more_menu_items(jobs, selected_ids),
    }


def structural_sig(jobs: list[Any]) -> tuple[Any, ...]:
    """Identity of the list (not live progress) — progress ticks must not rebuild."""
    return tuple((j.id, j.status, j.title, getattr(j, "thumbnail_path", None)) for j in jobs)
