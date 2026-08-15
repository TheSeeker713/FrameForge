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
CHOICE_FORCE_QUIT = "force_quit"
CHOICE_STAY = "stay"
CHOICE_QUIT_IDLE = "quit_idle"
CHOICES = (
    CHOICE_CANCEL_AND_QUIT,
    CHOICE_PAUSE_AND_QUIT,
    CHOICE_WAIT_THEN_QUIT,
)
ALL_QUIT_CHOICES = CHOICES + (CHOICE_FORCE_QUIT, CHOICE_STAY, CHOICE_QUIT_IDLE)

OUTCOME_EXIT = "exit"
OUTCOME_STAY = "stay"
OUTCOME_WAIT = "wait"
OUTCOME_FORCE = "force"


def list_active_work(repo: Any) -> list[Any]:
    """Jobs currently in downloading, upscaling, or converting (at most one)."""
    jobs: list[Any] = []
    for status in ("downloading", "upscaling", "converting"):
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
    """Apply a quit option. Returns exit / wait / stay / force."""
    if choice == CHOICE_STAY:
        return OUTCOME_STAY
    if choice == CHOICE_FORCE_QUIT:
        return OUTCOME_FORCE
    if choice == CHOICE_QUIT_IDLE:
        return OUTCOME_EXIT
    if choice not in CHOICES:
        raise ValueError(f"quit choice must be one of {ALL_QUIT_CHOICES}, got {choice!r}")
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


QUIT_DIALOG_TITLE = "Work in progress"
QUIT_OPTION_CANCEL = "Cancel download and quit"
QUIT_OPTION_PAUSE = "Pause download and quit"
QUIT_OPTION_WAIT = "Wait for download to complete, then quit"


def ask_quit_while_busy(parent: Any, *, wait: bool = True) -> str | None:
    """Show the three-option quit dialog. Returns a CHOICE_* or None (stay)."""
    import customtkinter as ctk

    result: list[str | None] = [None]
    win = ctk.CTkToplevel(parent)
    win.title(QUIT_DIALOG_TITLE)
    win.geometry("420x220")
    win.resizable(False, False)
    try:
        win.transient(parent)
    except Exception:  # noqa: BLE001
        pass
    ctk.CTkLabel(
        win,
        text="A download or upscale is still running.\nChoose how to quit:",
        justify="left",
    ).pack(anchor="w", padx=16, pady=(16, 12))

    def choose(choice: str) -> None:
        result[0] = choice
        win.destroy()

    ctk.CTkButton(
        win,
        text=QUIT_OPTION_CANCEL,
        command=lambda: choose(CHOICE_CANCEL_AND_QUIT),
    ).pack(fill="x", padx=16, pady=4)
    ctk.CTkButton(
        win,
        text=QUIT_OPTION_PAUSE,
        command=lambda: choose(CHOICE_PAUSE_AND_QUIT),
    ).pack(fill="x", padx=16, pady=4)
    ctk.CTkButton(
        win,
        text=QUIT_OPTION_WAIT,
        command=lambda: choose(CHOICE_WAIT_THEN_QUIT),
    ).pack(fill="x", padx=16, pady=4)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    if wait:
        try:
            win.grab_set()
        except Exception:  # noqa: BLE001
            pass
        parent.wait_window(win)
    return result[0]
