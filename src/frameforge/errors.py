"""Structured job error categories for GUI hints and persistence."""

from __future__ import annotations

import re
from typing import Any

from frameforge.download.auth_hints import (
    auth_action_hint,
    is_auth_failure,
    normalize_domain_safe,
)

AUTH_REQUIRED = "auth_required"
NETWORK = "network"
FFMPEG = "ffmpeg"
BLOCKED_4K = "blocked_4k"
CANCELLED = "cancelled"
UNKNOWN = "unknown"

CATEGORIES = (AUTH_REQUIRED, NETWORK, FFMPEG, BLOCKED_4K, CANCELLED, UNKNOWN)

_NETWORK_RE = re.compile(
    r"connection (reset|refused|aborted|timed? ?out)"
    r"|timed? ?out"
    r"|name or service not known"
    r"|getaddrinfo"
    r"|failed to resolve"
    r"|temporary failure in name resolution"
    r"|network is unreachable"
    r"|ssl(eof|error)?"
    r"|http error 429"
    r"|http error 50[234]"
    r"|errno \d+"
    r"|urlopen error",
    re.IGNORECASE,
)
_FFMPEG_RE = re.compile(
    r"\bffmpeg\b|\bffprobe\b|\blibx264\b|\baac\b encoder|no such file or directory",
    re.IGNORECASE,
)
_BLOCKED_4K_RE = re.compile(r"blocked:.*(?:4k|2160)|height\s*=\s*2[1-9]\d{2}", re.IGNORECASE)


def classify_error(message: str | None, *, status: str | None = None) -> str:
    """Map a human error string (and optional status) to a stable category."""
    if status == "cancelled":
        return CANCELLED
    text = str(message or "")
    lower = text.lower()
    if "cancelled" in lower and not is_auth_failure(text):
        return CANCELLED
    if is_auth_failure(text):
        return AUTH_REQUIRED
    if _BLOCKED_4K_RE.search(text) or ("blocked" in lower and "2160" in lower):
        return BLOCKED_4K
    if _FFMPEG_RE.search(text):
        return FFMPEG
    if _NETWORK_RE.search(text):
        return NETWORK
    return UNKNOWN


def suggested_action(category: str, *, auth_hint: str | None = None) -> str | None:
    if category == AUTH_REQUIRED:
        return auth_hint or (
            "Next: Authenticate this site / Import cookies, then Retry failed."
        )
    if category == NETWORK:
        return "Next: check the network connection, then Retry failed."
    if category == FFMPEG:
        return "Next: confirm FFmpeg is on PATH (`python -m frameforge --check-env`), then retry."
    if category == BLOCKED_4K:
        return "Next: select a lower-resolution source (≤1080p). 4K/≥2160p cannot be upscaled."
    if category == CANCELLED:
        return "Next: Retry failed or Download selected if you still want this item."
    if category == UNKNOWN:
        return "Next: Retry failed, or inspect the message above."
    return None


def format_error_panel(job: Any | None) -> str:
    """Category + human message + suggested next action for the GUI error panel."""
    if job is None:
        return ""
    err = getattr(job, "error", None)
    status = getattr(job, "status", None)
    opts = job.options() if hasattr(job, "options") else {}
    cat = opts.get("error_category")
    if not cat:
        cat = classify_error(err, status=status) if (err or status == "cancelled") else None
    if not err and status != "cancelled":
        return ""
    lines: list[str] = []
    if cat:
        lines.append(f"Category: {cat}")
    if err:
        lines.append(str(err))
    elif status == "cancelled":
        lines.append("Cancelled by user.")
    hint = opts.get("auth_hint") if cat == AUTH_REQUIRED else None
    action = suggested_action(cat or UNKNOWN, auth_hint=hint)
    if action and action not in "\n".join(lines):
        lines.append("")
        lines.append(action)
    return "\n".join(lines)


def annotate_job_error(
    repo: Any,
    job_id: int,
    message: str,
    *,
    status: str = "failed",
    url: str | None = None,
) -> Any:
    """Persist human error + error_category (and auth hint when applicable)."""
    job = repo.get(job_id)
    url = url or job.url
    cat = classify_error(message, status=status)
    repo.update_status(job_id, status, error=str(message))
    patch: dict[str, Any] = {"error_category": cat}
    if cat == AUTH_REQUIRED:
        patch["auth_required"] = True
        patch["auth_hint"] = auth_action_hint(url)
        patch["auth_domain"] = normalize_domain_safe(url)
    else:
        patch["auth_required"] = False
    return repo.merge_options(job_id, patch)
