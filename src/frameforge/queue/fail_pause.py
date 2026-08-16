"""Pause the sequential queue after a serious download failure (bot/auth)."""

from __future__ import annotations

from typing import Any

from frameforge.errors import (
    OUTPUT_MISSING,
    DISK_SPACE,
    UPSCALE_LIMIT,
    classify_error,
    human_cause,
    should_fail_pause,
    suggested_actions,
)

FAIL_PAUSE_SETTING = "fail_pause_on_auth"
FAIL_PAUSE_ANY_SETTING = "fail_pause_on_any"

MODAL_ACTIONS: tuple[tuple[str, str], ...] = (
    ("import_browser", "Import from browser"),
    ("authenticate", "Authenticate site"),
    ("retry", "Retry this job"),
    ("skip_resume", "Skip & resume queue"),
    ("stop", "Stop queue"),
)

OUTPUT_MISSING_ACTIONS: tuple[tuple[str, str], ...] = (
    ("retry", "Retry this job"),
    ("open_folder", "Open folder"),
    ("skip_resume", "Skip & resume queue"),
    ("stop", "Stop queue"),
)


def modal_actions_for(category: str | None, *, archive_hit: bool = False) -> tuple[tuple[str, str], ...]:
    if category == OUTPUT_MISSING:
        retry = ("retry", "Force re-download" if archive_hit else "Retry this job")
        return (retry, *OUTPUT_MISSING_ACTIONS[1:])
    if category in (DISK_SPACE, UPSCALE_LIMIT):
        return (
            ("retry", "Retry this job"),
            ("skip_resume", "Skip & resume queue"),
            ("stop", "Stop queue"),
        )
    return MODAL_ACTIONS


def fail_pause_enabled(repo: Any) -> bool:
    get = getattr(repo, "get_setting", None)
    if get is None:
        return True
    return str(get(FAIL_PAUSE_SETTING, "1") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def fail_pause_on_any(repo: Any) -> bool:
    get = getattr(repo, "get_setting", None)
    if get is None:
        return False
    return str(get(FAIL_PAUSE_ANY_SETTING, "0") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def maybe_fail_pause(worker: Any, repo: Any, job: Any) -> bool:
    """Disarm the worker after bot/auth (or any) failure. Never claims the next job."""
    if getattr(job, "status", None) != "failed":
        return False
    if not fail_pause_enabled(repo) and not fail_pause_on_any(repo):
        return False
    opts = job.options() if hasattr(job, "options") else {}
    cat = opts.get("error_category") or classify_error(
        getattr(job, "error", None), url=getattr(job, "url", None)
    )
    if fail_pause_on_any(repo) or should_fail_pause(cat):
        halt = getattr(worker, "halt_after_fail", None)
        if callable(halt):
            halt()
        else:
            worker.disarm()
        if hasattr(repo, "merge_options"):
            repo.merge_options(job.id, {"fail_pause": True})
        return True
    return False


def fail_pause_payload(job: Any) -> dict[str, Any]:
    """Plain-language modal fields (no Tk)."""
    opts = job.options() if hasattr(job, "options") else {}
    cat = opts.get("error_category") or classify_error(
        getattr(job, "error", None), url=getattr(job, "url", None)
    )
    archive_hit = bool(opts.get("archive_hit")) or "archive lists this video" in str(
        getattr(job, "error", None) or ""
    ).lower()
    return {
        "job_id": getattr(job, "id", None),
        "title": getattr(job, "title", None) or "",
        "url": getattr(job, "url", None) or "",
        "category": cat,
        "cause": opts.get("error_cause") or human_cause(cat),
        "error": getattr(job, "error", None) or "",
        "actions": list(opts.get("error_actions") or suggested_actions(cat)),
        "buttons": [
            {"id": aid, "label": label}
            for aid, label in modal_actions_for(cat, archive_hit=archive_hit)
        ],
        "archive_hit": archive_hit,
    }
