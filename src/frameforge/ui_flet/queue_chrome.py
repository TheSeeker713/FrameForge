"""Visibility predicates for the always-on queue action row (no selection required)."""

from __future__ import annotations

from typing import Any

from frameforge.db.repository import TERMINAL_STATUSES


def queue_chrome_spec(
    jobs: list[Any],
    selected_ids: set[int],
    *,
    undo_available: bool = False,
    armed: bool = False,
) -> dict[str, Any]:
    """Buttons appear only when relevant. Clear selected is enabled iff selection ≥ 1.

    BLOCKED 4K+ rows are ``completed`` with a badge — they count as finished, not failed.
    Chrome stays visible after a full clear if Undo is available.
    """
    if not jobs and not undo_available:
        return {
            "visible": False,
            "show_download_all": False,
            "show_retry_failed": False,
            "show_clear_finished": False,
            "clear_selected_enabled": False,
            "show_undo": False,
            "show_pause": False,
            "show_stop": False,
            "pending_count": 0,
            "failed_count": 0,
            "finished_count": 0,
        }
    pending = sum(1 for j in jobs if getattr(j, "status", None) == "pending")
    failed = sum(1 for j in jobs if getattr(j, "status", None) == "failed")
    finished = sum(1 for j in jobs if getattr(j, "status", None) in TERMINAL_STATUSES)
    active = any(
        getattr(j, "status", None) in {"downloading", "upscaling", "converting"} for j in jobs
    )
    transport = bool(active or armed)
    return {
        "visible": True,
        "show_download_all": pending > 0 and not transport,
        "show_retry_failed": failed > 0,
        "show_clear_finished": finished > 0,
        "clear_selected_enabled": len(selected_ids) >= 1,
        "show_undo": undo_available,
        "show_pause": transport,
        "show_stop": transport,
        "pending_count": pending,
        "failed_count": failed,
        "finished_count": finished,
    }
