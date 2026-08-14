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
BOT_CHECK = "bot_check"
RATE_LIMITED = "rate_limited"
NOT_AVAILABLE = "not_available"
NETWORK = "network"
FFMPEG = "ffmpeg"
BLOCKED_4K = "blocked_4k"
CANCELLED = "cancelled"
UNKNOWN = "unknown"

CATEGORIES = (
    AUTH_REQUIRED,
    BOT_CHECK,
    RATE_LIMITED,
    NOT_AVAILABLE,
    NETWORK,
    FFMPEG,
    BLOCKED_4K,
    CANCELLED,
    UNKNOWN,
)

# Failures that should pause a bulk run (bot/auth and hard unknown).
FAIL_PAUSE_CATEGORIES = frozenset({AUTH_REQUIRED, BOT_CHECK, UNKNOWN})
STDERR_TAIL_LINES = 12
STDERR_TAIL_CHARS = 2000

_BOT_RE = re.compile(
    r"sign in to confirm"
    r"|you.?re not a bot"
    r"|you are not a bot"
    r"|not a bot"
    r"|bot.?check"
    r"|bot detection"
    r"|recaptcha"
    r"|hcaptcha"
    r"|unusual traffic"
    r"|confirm you.?re (a )?human"
    r"|verify you are (a )?human"
    r"|please complete the security check"
    r"|automated (queries|traffic|access|requests)"
    r"|detected unusual",
    re.IGNORECASE,
)
_RATE_RE = re.compile(
    r"http error 429"
    r"|status code 429"
    r"|too many requests"
    r"|rate[- ]limit"
    r"|slow down"
    r"|429 too many",
    re.IGNORECASE,
)
_UNAVAIL_RE = re.compile(
    r"video unavailable"
    r"|this video is (private|unavailable)"
    r"|private video"
    r"|has been (removed|deleted)"
    r"|copyright"
    r"|not (currently )?available"
    r"|http error 404"
    r"|status code 404",
    re.IGNORECASE,
)
_NETWORK_RE = re.compile(
    r"connection (reset|refused|aborted|timed? ?out)"
    r"|timed? ?out"
    r"|name or service not known"
    r"|getaddrinfo"
    r"|failed to resolve"
    r"|temporary failure in name resolution"
    r"|network is unreachable"
    r"|ssl(eof|error)?"
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
    if "cancelled" in lower and not is_auth_failure(text) and not _BOT_RE.search(text):
        return CANCELLED
    if _BOT_RE.search(text):
        return BOT_CHECK
    if _RATE_RE.search(text):
        return RATE_LIMITED
    if _UNAVAIL_RE.search(text):
        return NOT_AVAILABLE
    if is_auth_failure(text):
        return AUTH_REQUIRED
    if _BLOCKED_4K_RE.search(text) or ("blocked" in lower and "2160" in lower):
        return BLOCKED_4K
    if _FFMPEG_RE.search(text):
        return FFMPEG
    if _NETWORK_RE.search(text):
        return NETWORK
    return UNKNOWN


def stderr_tail(message: str | None, *, max_lines: int = STDERR_TAIL_LINES) -> str:
    """Last non-empty lines of yt-dlp/ffmpeg output for the error panel."""
    lines = [ln.strip() for ln in str(message or "").splitlines() if ln.strip()]
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > STDERR_TAIL_CHARS:
        return tail[-STDERR_TAIL_CHARS:]
    return tail


def format_ytdlp_exit_error(rc: int, lines: list[str] | tuple[str, ...], *, max_lines: int = STDERR_TAIL_LINES) -> str:
    """Combine exit code with a stderr/stdout tail so classifiers see bot/auth text."""
    tail = stderr_tail("\n".join(lines), max_lines=max_lines)
    if tail:
        return f"yt-dlp exited with code {rc}\n{tail}"
    return f"yt-dlp exited with code {rc}"


def human_cause(category: str) -> str:
    return {
        AUTH_REQUIRED: "This site wants you signed in (cookies or login).",
        BOT_CHECK: "The site thinks this is automated traffic (bot check).",
        RATE_LIMITED: "The site is rate-limiting requests (HTTP 429 / slow down).",
        NOT_AVAILABLE: "The video is private, removed, or otherwise unavailable.",
        NETWORK: "A network error interrupted the download.",
        FFMPEG: "FFmpeg/ffprobe failed while processing the file.",
        BLOCKED_4K: "This source is 4K/≥2160p and cannot be upscaled here.",
        CANCELLED: "The job was cancelled.",
        UNKNOWN: "The download failed for an unclassified reason.",
    }.get(category, "The download failed.")


def suggested_actions(category: str) -> list[str]:
    if category in (AUTH_REQUIRED, BOT_CHECK):
        return [
            "Import from browser (Firefox preferred)",
            "Authenticate site / Import cookies.txt",
            "Retry this job",
        ]
    if category == RATE_LIMITED:
        return [
            "Wait a few minutes, then retry",
            "Import cookies if the site is logged-in only",
            "Enable gentle rate mode in Settings after resume",
        ]
    if category == NOT_AVAILABLE:
        return ["Skip this job — it cannot be downloaded"]
    if category == NETWORK:
        return ["Check the network connection", "Retry this job"]
    if category == FFMPEG:
        return ["Confirm FFmpeg is on PATH (`python -m frameforge --check-env`)", "Retry"]
    if category == BLOCKED_4K:
        return ["Select a lower-resolution source (≤1080p)"]
    if category == CANCELLED:
        return ["Re-download or Download selected if you still want this item"]
    return ["Retry failed", "Inspect the error message"]


def suggested_action(category: str, *, auth_hint: str | None = None) -> str | None:
    if category in (AUTH_REQUIRED, BOT_CHECK) and auth_hint:
        return auth_hint
    actions = suggested_actions(category)
    if not actions:
        return None
    return "Next: " + "; ".join(actions) + "."


def should_fail_pause(category: str | None) -> bool:
    return category in FAIL_PAUSE_CATEGORIES


def format_error_panel(job: Any | None) -> str:
    """Category + human cause + message + suggested next actions."""
    if job is None:
        return ""
    err = getattr(job, "error", None)
    status = getattr(job, "status", None)
    opts = job.options() if hasattr(job, "options") else {}
    cat = opts.get("error_category")
    if status == "paused":
        return "Paused. Resume when you want this download to continue."
    if not cat:
        cat = classify_error(err, status=status) if (err or status == "cancelled") else None
    if not err and status != "cancelled":
        return ""
    lines: list[str] = []
    if cat:
        lines.append(f"Category: {cat}")
        lines.append(f"Cause: {opts.get('error_cause') or human_cause(cat)}")
    if err:
        lines.append(str(err))
    elif status == "cancelled":
        lines.append("Cancelled by user.")
    hint = opts.get("auth_hint") if cat in (AUTH_REQUIRED, BOT_CHECK) else None
    action = suggested_action(cat or UNKNOWN, auth_hint=hint)
    if action and action not in "\n".join(lines):
        lines.append("")
        lines.append(action)
    stored = opts.get("error_actions")
    if isinstance(stored, list) and stored:
        extra = "Actions: " + " / ".join(str(a) for a in stored)
        if extra not in "\n".join(lines):
            lines.append(extra)
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
    patch: dict[str, Any] = {
        "error_category": cat,
        "error_cause": human_cause(cat) or "The download failed.",
        "error_actions": suggested_actions(cat),
        "error_stderr_tail": stderr_tail(message),
    }
    if cat in (AUTH_REQUIRED, BOT_CHECK):
        patch["auth_required"] = True
        patch["auth_hint"] = auth_action_hint(url)
        patch["auth_domain"] = normalize_domain_safe(url)
    else:
        patch["auth_required"] = False
    return repo.merge_options(job_id, patch)
