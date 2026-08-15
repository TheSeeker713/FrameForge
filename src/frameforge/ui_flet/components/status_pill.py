"""Header status pill text (Idle • N ready | Downloading • speed | …)."""

from __future__ import annotations

from typing import Any


def status_pill_text(
    *,
    active_status: str | None,
    pending_count: int = 0,
    speed_str: str | None = None,
    paused: bool = False,
    idle_reason: str | None = None,
) -> str:
    if paused or active_status == "paused":
        return "Paused"
    if active_status == "downloading":
        speed = speed_str or "…"
        return f"Downloading • {speed}"
    if active_status == "upscaling":
        return "Upscaling"
    if active_status == "converting":
        return "Converting"
    n = max(0, int(pending_count))
    if n and idle_reason == "stopped":
        return f"Idle • {n} ready — stopped"
    if n and idle_reason == "fail_pause":
        return f"Idle • {n} ready — queue paused after failure"
    return f"Idle • {n} ready"


def status_from_repo(
    repo: Any, worker: Any | None = None, *, idle_reason: str | None = None
) -> str:
    paused = False
    active = None
    speed = None
    if worker is not None and not getattr(worker, "is_armed", False):
        # still show active stage if one is in flight
        pass
    for status in ("downloading", "upscaling", "converting"):
        jobs = list(repo.list_jobs(status))
        if jobs:
            active = status
            opts = jobs[0].options() if hasattr(jobs[0], "options") else {}
            speed = opts.get("speed_str") or opts.get("live_speed")
            break
    paused_jobs = list(repo.list_jobs("paused")) if active is None else []
    if active is None and paused_jobs:
        paused = True
    pending = repo.count_by_status("pending")
    return status_pill_text(
        active_status=active,
        pending_count=pending,
        speed_str=speed,
        paused=paused,
        idle_reason=idle_reason,
    )
