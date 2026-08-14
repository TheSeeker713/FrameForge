"""Validate Netscape cookies before resuming a bot-paused queue."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from frameforge.download.cookies import (
    cookie_path_for_url,
    has_cookies,
    is_netscape_cookie_text,
    normalize_domain,
)
from frameforge.errors import AUTH_REQUIRED, BOT_CHECK, classify_error

Probe = Callable[[str, Path], Any]

UNLOCK_FAIL = (
    "Cookies did not unlock this site — try browser login then import again."
)
GENTLE_AFTER_BOT_JOBS = 3
GENTLE_JOBS_LEFT_SETTING = "gentle_jobs_left"

_session_validated: dict[str, float] = {}


@dataclass
class CookieValidationResult:
    ok: bool
    message: str
    domain: str | None = None
    cookiefile: Path | None = None
    probed: bool = False


def clear_session_cookie_validation() -> None:
    _session_validated.clear()


def cookies_validated_in_session(domain_or_url: str) -> bool:
    try:
        domain = normalize_domain(domain_or_url)
    except ValueError:
        return False
    return domain in _session_validated


def mark_cookies_validated(domain_or_url: str) -> None:
    domain = normalize_domain(domain_or_url)
    _session_validated[domain] = time.time()


def enable_gentle_after_bot(repo: Any, n: int = GENTLE_AFTER_BOT_JOBS) -> int:
    """Cooldown for the next N jobs only — does not permanently enable gentle_rate_mode."""
    repo.set_setting(GENTLE_JOBS_LEFT_SETTING, str(max(0, int(n))))
    return n


def consume_gentle_job(repo: Any) -> bool:
    """True when this download should use gentle rate. Decrements the bot-recovery counter."""
    if str(repo.get_setting("gentle_rate_mode", "0") or "0") == "1":
        return True
    try:
        left = int(repo.get_setting(GENTLE_JOBS_LEFT_SETTING, "0") or 0)
    except ValueError:
        left = 0
    if left <= 0:
        return False
    repo.set_setting(GENTLE_JOBS_LEFT_SETTING, str(left - 1))
    return True


def _file_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return is_netscape_cookie_text(text)


def _default_probe(url: str, cookiefile: Path) -> Any:
    from frameforge.download.ytdlp import YtDlpDownloader

    return YtDlpDownloader(cookiefile=cookiefile).extract_info(url)


def validate_cookies_for_url(
    url: str,
    *,
    probe: Probe | None = None,
    skip_probe_if_session: bool = True,
) -> CookieValidationResult:
    """Check on-disk Netscape cookies, then optionally probe the host (injectable, no GUI)."""
    try:
        domain = normalize_domain(url)
    except ValueError as exc:
        return CookieValidationResult(False, str(exc))
    path = cookie_path_for_url(url)
    if not has_cookies(url) or not _file_ok(path):
        return CookieValidationResult(
            False,
            "No valid Netscape cookies for this site. Import from Firefox or cookies.txt first.",
            domain=domain,
            cookiefile=path,
        )
    if skip_probe_if_session and cookies_validated_in_session(domain):
        return CookieValidationResult(
            True,
            f"Cookies already validated for {domain} this session.",
            domain=domain,
            cookiefile=path,
            probed=False,
        )
    run = probe if probe is not None else _default_probe
    try:
        info = run(url, path)
    except Exception as exc:  # noqa: BLE001
        cat = classify_error(str(exc))
        if cat in {BOT_CHECK, AUTH_REQUIRED}:
            msg = UNLOCK_FAIL
        else:
            msg = f"{UNLOCK_FAIL} ({exc})"
        return CookieValidationResult(False, msg, domain=domain, cookiefile=path, probed=True)
    if not isinstance(info, dict) or not (info.get("id") or info.get("title") or info.get("webpage_url")):
        return CookieValidationResult(
            False,
            UNLOCK_FAIL,
            domain=domain,
            cookiefile=path,
            probed=True,
        )
    mark_cookies_validated(domain)
    return CookieValidationResult(
        True,
        f"Cookies look valid for {domain}.",
        domain=domain,
        cookiefile=path,
        probed=True,
    )
