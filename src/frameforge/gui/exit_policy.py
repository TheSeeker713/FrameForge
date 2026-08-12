"""Central exit policy for window close, menu Quit, and tray Quit.

If no active download/upscale (and wait-to-quit is not in progress), callers
may exit immediately. If work is active, they must obtain an explicit choice
instead of exiting silently.
"""

from __future__ import annotations

from typing import Any

QUIT_NOW = "quit_now"
NEEDS_CHOICE = "needs_choice"
WAIT_IN_PROGRESS = "wait_in_progress"

CHOICE_CANCEL_AND_QUIT = "cancel_and_quit"
CHOICE_PAUSE_AND_QUIT = "pause_and_quit"
CHOICE_WAIT_THEN_QUIT = "wait_then_quit"
CHOICES = (
    CHOICE_CANCEL_AND_QUIT,
    CHOICE_PAUSE_AND_QUIT,
    CHOICE_WAIT_THEN_QUIT,
)

OUTCOME_EXIT = "exit"
OUTCOME_STAY = "stay"
OUTCOME_WAIT = "wait"


def list_active_work(repo: Any) -> list[Any]:
    """Jobs currently in downloading or upscaling (at most one in FrameForge)."""
    jobs: list[Any] = []
    for status in ("downloading", "upscaling"):
        jobs.extend(list(repo.list_jobs(status)))
    return jobs


def wait_to_quit_active(worker: Any) -> bool:
    return bool(getattr(worker, "wait_to_quit", False))


def classify_exit(repo: Any, worker: Any | None = None) -> str:
    """How the caller should proceed.

    *quit_now* — no active stage; safe to exit.
    *needs_choice* — active download/upscale; do not exit silently.
    *wait_in_progress* — user already chose wait-then-quit; stay until idle.
    """
    waiting = wait_to_quit_active(worker) if worker is not None else False
    active = list_active_work(repo)
    if waiting:
        return WAIT_IN_PROGRESS if active else QUIT_NOW
    if active:
        return NEEDS_CHOICE
    return QUIT_NOW


def apply_quit_choice(worker: Any, choice: str) -> str:
    """Apply one of the three quit options. Returns exit / wait / stay."""
    if choice not in CHOICES:
        raise ValueError(f"quit choice must be one of {CHOICES}, got {choice!r}")
    jobs = list_active_work(worker.repo)
    if choice == CHOICE_CANCEL_AND_QUIT:
        for job in jobs:
            worker.cancel_job(job.id)
        if hasattr(worker, "clear_wait_to_quit"):
            worker.clear_wait_to_quit()
        worker.disarm()
        return OUTCOME_EXIT
    if choice == CHOICE_PAUSE_AND_QUIT:
        for job in jobs:
            worker.pause_job(job.id)
        if hasattr(worker, "clear_wait_to_quit"):
            worker.clear_wait_to_quit()
        return OUTCOME_EXIT
    # wait_then_quit
    if hasattr(worker, "begin_wait_to_quit"):
        worker.begin_wait_to_quit()
    else:
        worker.disarm()
    return OUTCOME_WAIT
