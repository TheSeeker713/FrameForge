"""Which queue actions are valid for a job's current state."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def can_download(job: Any) -> bool:
    return getattr(job, "status", None) == "pending"


def can_retry_download(job: Any) -> bool:
    """Failed or cancelled rows can be returned to pending (does not auto-start)."""
    return getattr(job, "status", None) in {"failed", "cancelled"}


def can_upscale(job: Any) -> bool:
    if getattr(job, "status", None) != "completed":
        return False
    src = getattr(job, "download_path", None) or getattr(job, "output_path", None)
    return bool(src) and Path(src).is_file()


def can_convert(job: Any) -> bool:
    if getattr(job, "status", None) != "completed":
        return False
    src = getattr(job, "output_path", None) or getattr(job, "download_path", None)
    return bool(src) and Path(src).is_file()


def can_cancel(job: Any) -> bool:
    return getattr(job, "status", None) in {
        "pending",
        "downloading",
        "upscaling",
        "converting",
        "convert_pending",
        "download_completed",
        "paused",
    }


def can_pause(job: Any) -> bool:
    return getattr(job, "status", None) in {"downloading", "upscaling", "converting"}


def can_resume(job: Any) -> bool:
    return getattr(job, "status", None) == "paused"


def can_clear_from_queue(job: Any) -> bool:
    """True when the job can leave the live queue (not an in-flight media stage)."""
    return getattr(job, "status", None) not in {
        "downloading",
        "upscaling",
        "converting",
    }
