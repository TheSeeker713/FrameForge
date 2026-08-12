"""Map download failures to recoverable auth / cookie hints."""

from __future__ import annotations

import re
from typing import Any

from frameforge.download.cookies import has_cookies, normalize_domain

AUTH_ACTION_LABEL = "Authenticate this site / Import cookies"

_AUTH_RE = re.compile(
    r"sign in to confirm"
    r"|you.?re not a bot"
    r"|you are not a bot"
    r"|not a bot"
    r"|login required"
    r"|please sign in"
    r"|please log in"
    r"|age[- ]restricted"
    r"|confirm your age"
    r"|members[- ]only"
    r"|join this channel"
    r"|http error 401"
    r"|status code 401"
    r"|401 unauthorized"
    r"|http error 403"
    r"|use --cookies"
    r"|cookies? (are )?needed"
    r"|authentication required"
    r"|this video is private"
    r"|private video"
    r"|sign in to watch",
    re.IGNORECASE,
)


def is_auth_failure(message: str | None) -> bool:
    """True when a downloader error clearly indicates login / bot / cookie gates."""
    if not message:
        return False
    return _AUTH_RE.search(str(message)) is not None


def auth_action_hint(url_or_domain: str | None = None) -> str:
    """User-facing next step. Never auto-opens a browser."""
    domain = ""
    cookies_exist = False
    if url_or_domain:
        try:
            domain = normalize_domain(url_or_domain)
            cookies_exist = has_cookies(url_or_domain)
        except ValueError:
            domain = ""
            cookies_exist = False
    if cookies_exist and domain:
        return (
            f"{AUTH_ACTION_LABEL}: cookies already exist for {domain}. "
            "Import to replace if they are stale, then retry the job."
        )
    if domain:
        return (
            f"{AUTH_ACTION_LABEL} for {domain}: open Authenticate site…, "
            "log in / accept gates, export Netscape cookies.txt, then import."
        )
    return (
        f"{AUTH_ACTION_LABEL}: open Authenticate site…, log in / accept gates, "
        "export Netscape cookies.txt, then import."
    )


def job_needs_auth(job: Any) -> bool:
    if job is None:
        return False
    opts = job.options() if hasattr(job, "options") else {}
    if opts.get("auth_required"):
        return True
    return is_auth_failure(getattr(job, "error", None))


def apply_auth_failure(repo: Any, job_id: int, message: str, url: str | None = None) -> Any:
    """Mark job failed with a clear error and structured auth hint in options_json."""
    job = repo.get(job_id)
    url = url or job.url
    hint = auth_action_hint(url)
    domain = ""
    try:
        domain = normalize_domain(url) if url else ""
    except ValueError:
        domain = ""
    repo.update_status(job_id, "failed", error=str(message))
    return repo.merge_options(
        job_id,
        {
            "auth_required": True,
            "auth_hint": hint,
            "auth_domain": domain or None,
        },
    )
