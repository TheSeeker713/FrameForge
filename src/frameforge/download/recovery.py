"""Automatic download recovery ladder (native, impersonate, cookies, generic)."""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from frameforge.download.auth_hints import is_auth_failure
from frameforge.errors import (
    AUTH_REQUIRED,
    BOT_CHECK,
    CANCELLED,
    DB_ERROR,
    DISK_SPACE,
    DRM_BLOCKED,
    IMPERSONATION_MISSING,
    JS_RUNTIME,
    NETWORK,
    NOT_AVAILABLE,
    OUTPUT_MISSING,
    RATE_LIMITED,
    UNKNOWN,
    UPSCALE_CONFIG,
    UPSCALE_LIMIT,
    classify_error,
)

SILENT_COOKIES_SETTING = "silent_browser_cookies"
AUTO_COOKIE_SETTING = "auto_cookie_recovery"
BACKOFF_SETTING = "auto_retry_backoff_sec"
JITTER_SETTING = "auto_retry_backoff_jitter_sec"
DEFAULT_BACKOFF_SEC = 5.0
DEFAULT_JITTER_SEC = 2.0
GENERIC_EXTRACTORS_CLI = "generic,default"
SILENT_FIREFOX_COOKIES = "silent_firefox_cookies"
BOT_RETRY = "bot_retry"
RETRY = "retry"
COOKIE_ATTEMPT_NAMES = frozenset({"cookies", SILENT_FIREFOX_COOKIES})
SILENT_IMPORT_TIMEOUT_SEC = 60
AUTO_COOKIE_BROWSERS = ("firefox", "edge")

log = logging.getLogger(__name__)

# Do not auto-generic-retry these.
SKIP_GENERIC_CATEGORIES = frozenset(
    {
        NOT_AVAILABLE,
        DRM_BLOCKED,
        CANCELLED,
        DISK_SPACE,
        DB_ERROR,
        JS_RUNTIME,
        OUTPUT_MISSING,
    }
)

# Silent browser cookies never run for these (even with auth-like wording).
SKIP_COOKIE_CATEGORIES = frozenset(
    {
        NOT_AVAILABLE,
        DRM_BLOCKED,
        DISK_SPACE,
        DB_ERROR,
        CANCELLED,
        JS_RUNTIME,
        UPSCALE_LIMIT,
        UPSCALE_CONFIG,
    }
)

_GENERIC_MISMATCH_RE = re.compile(
    r"unsupported url"
    r"|no suitable extractor"
    r"|unsupported website"
    r"|extractor.+mismatch"
    r"|unable to extract"
    r"|no video could be found"
    r"|there's no video"
    r"|unsupported webpage"
    r"|use --use-extractors"
    r"|generic extractor",
    re.IGNORECASE,
)

_FINGERPRINT_RE = re.compile(
    r"tls.?fingerprint"
    r"|ja3"
    r"|browser impersonat"
    r"|impersonated requests"
    r"|curl_cffi"
    r"|cloudflare.*(103|challenge|blocked the request)",
    re.IGNORECASE,
)

_SOFT_AUTH_RE = re.compile(
    r"age[- ]?(gate|verif)"
    r"|verify your age"
    r"|you must be 18"
    r"|registered users"
    r"|fresh cookies"
    r"|cookies? (expired|invalid|are needed)"
    r"|--cookies-from-browser"
    r"|only available (to|for)"
    r"|join (pornhub|this (site|channel))"
    r"|premium (members|only)"
    r"|login required"
    r"|please sign in",
    re.IGNORECASE,
)

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_fingerprint(message: str | None) -> bool:
    return bool(_FINGERPRINT_RE.search(str(message or "")))


def looks_like_generic_mismatch(message: str | None) -> bool:
    return bool(_GENERIC_MISMATCH_RE.search(str(message or "")))


def looks_like_auth_wall(message: str | None, *, url: str | None = None) -> bool:
    """True for login/age/bot/cookie walls in stderr (any host)."""
    text = str(message or "")
    return bool(is_auth_failure(text) or _SOFT_AUTH_RE.search(text))


COOKIE_ELIGIBLE_CATEGORIES = frozenset(
    {
        AUTH_REQUIRED,
        BOT_CHECK,
        RATE_LIMITED,
        IMPERSONATION_MISSING,
    }
)


def cookie_domain_eligible(
    url: str | None,
    message: str | None = None,
    attempts: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """True when this URL/job should try domain cookies (any host, not PH-only).

    Signals: auth-like stderr, Auto-impersonate host (cookies usually required
    after TLS impersonate), or this failure chain already used impersonate.

    An existing Netscape file is **not** a reason to re-import from Firefox.
    Unknown + cookies-on-disk used to hang the worker on every YouTube fail.
    """
    if looks_like_auth_wall(message, url=url):
        return True
    if not is_http_url(url):
        return False
    try:
        from frameforge.download.impersonate import url_needs_impersonate

        if url_needs_impersonate(url):
            return True
    except Exception:  # noqa: BLE001
        pass
    done = {str(a).strip().lower() for a in (attempts or []) if str(a).strip()}
    if "impersonate" in done:
        return True
    return False


def should_try_silent_cookies(
    category: str | None,
    message: str | None = None,
    url: str | None = None,
    attempts: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """Whether this failure may take one silent Firefox (then Edge) cookie import.

    Site-agnostic: any http(s) job URL. Host/extractor is not a gate.
    """
    cat = category or classify_error(message, url=url)
    if cat in SKIP_COOKIE_CATEGORIES:
        return False
    if not is_http_url(url):
        return False
    if cat in {OUTPUT_MISSING, NETWORK} and not looks_like_auth_wall(message, url=url):
        return False
    if cat in COOKIE_ELIGIBLE_CATEGORIES:
        return True
    if looks_like_auth_wall(message, url=url):
        return True
    if cat == UNKNOWN and cookie_domain_eligible(url, message, attempts):
        return True
    return False


def is_http_url(url: str | None) -> bool:
    text = str(url or "").strip()
    if _HTTP_URL_RE.match(text):
        return True
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _setting_on(repo: Any | None, key: str, default: str = "1") -> bool:
    if repo is None or not hasattr(repo, "get_setting"):
        return True
    return str(repo.get_setting(key, default) or default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def silent_cookies_enabled(repo: Any | None) -> bool:
    """ON unless auto_cookie_recovery or legacy silent_browser_cookies is off."""
    return _setting_on(repo, AUTO_COOKIE_SETTING, "1") and _setting_on(
        repo, SILENT_COOKIES_SETTING, "1"
    )


def auto_retry_backoff_sec(repo: Any | None) -> float:
    if repo is None or not hasattr(repo, "get_setting"):
        return DEFAULT_BACKOFF_SEC
    raw = repo.get_setting(BACKOFF_SETTING, str(int(DEFAULT_BACKOFF_SEC)))
    try:
        return max(0.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_BACKOFF_SEC


def auto_retry_backoff_jitter_sec(repo: Any | None) -> float:
    if repo is None or not hasattr(repo, "get_setting"):
        return DEFAULT_JITTER_SEC
    raw = repo.get_setting(JITTER_SETTING, str(int(DEFAULT_JITTER_SEC)))
    try:
        return max(0.0, min(15.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_JITTER_SEC


def compute_retry_delay(repo: Any | None) -> float:
    """Base backoff plus optional jitter. Zero base means no wait (jitter ignored)."""
    base = auto_retry_backoff_sec(repo)
    if base <= 0:
        return 0.0
    jitter = auto_retry_backoff_jitter_sec(repo)
    extra = random.uniform(0.0, jitter) if jitter > 0 else 0.0
    return base + extra


def waiting_label(seconds: float) -> str:
    if abs(seconds - round(seconds)) < 0.05:
        return f"Waiting {int(round(seconds))}s before retry…"
    return f"Waiting {seconds:.1f}s before retry…"


def format_backoff_attempt(seconds: float) -> str:
    return f"backoff:{seconds:.1f}"


def backoff_already_applied(attempts: list[str] | tuple[str, ...] | None) -> bool:
    return any(str(a).strip().lower().startswith("backoff:") for a in (attempts or []))


def interruptible_backoff(seconds: float, should_abort: Callable[[], bool]) -> bool:
    """Return True if full wait completed, False if aborted. Worker thread only."""
    end = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return True
        if should_abort():
            return False
        time.sleep(min(0.5, remaining))


def recovery_should_abort(
    job_id: int,
    repo: Any,
    process_registry: Any | None = None,
) -> str | None:
    """Return 'cancelled', 'paused', or None. Never touches the UI thread."""
    try:
        current = repo.get(job_id)
    except Exception:  # noqa: BLE001
        return None
    status = getattr(current, "status", None)
    if status == "cancelled":
        return "cancelled"
    if status == "paused":
        return "paused"
    if process_registry is not None:
        if process_registry.was_killed(job_id):
            return "cancelled"
        if process_registry.was_paused(job_id):
            return "paused"
    return None


def apply_auto_retry_backoff(
    *,
    repo: Any,
    attempts: list[str],
    job_id: int,
    progress_cb: Callable[..., Any] | None = None,
    process_registry: Any | None = None,
) -> bool:
    """Wait once on the worker thread before an automatic retry. False if aborted."""
    if backoff_already_applied(attempts):
        return True
    delay = compute_retry_delay(repo)
    if delay <= 0:
        return True
    label = waiting_label(delay)
    if progress_cb:
        progress_cb(
            0.0,
            {
                "speed_bps": None,
                "eta_seconds": None,
                "speed_str": label,
                "eta_str": None,
            },
        )

    def should_abort() -> bool:
        return recovery_should_abort(job_id, repo, process_registry) is not None

    if not interruptible_backoff(delay, should_abort):
        return False
    attempts.append(format_backoff_attempt(delay))
    if hasattr(repo, "merge_options"):
        repo.merge_options(
            job_id,
            {
                "recovery_attempts": list(attempts),
                "recovery_tried": format_tried(attempts),
            },
        )
    return True


def format_tried(attempts: list[str] | tuple[str, ...] | None) -> str:
    names = [str(a).strip() for a in (attempts or []) if str(a).strip()]
    if not names:
        return ""
    return "tried: " + ", ".join(names)


def cookies_attempt_done(attempts: list[str] | tuple[str, ...] | None) -> bool:
    done = {str(a).strip().lower() for a in (attempts or []) if str(a).strip()}
    return bool(done & COOKIE_ATTEMPT_NAMES)


def next_recovery_step(
    attempts: list[str] | tuple[str, ...] | None,
    *,
    category: str | None,
    message: str | None = None,
    url: str | None = None,
    impersonated: bool = False,
    has_impersonate_targets: bool = False,
    silent_cookies: bool = True,
) -> str | None:
    """Return the next automatic step: impersonate | silent_firefox_cookies | bot_retry | generic, or None.

    Order after the in-download aria2→native fallback:
    impersonate → silent Firefox cookies (any http(s) domain) → one bot/rate retry
    without cookies if cookies were skipped → generic once.
    """
    done = {str(a).strip().lower() for a in (attempts or []) if str(a).strip()}
    cat = category or classify_error(message, url=url)
    text = str(message or "")

    if cat == CANCELLED:
        return None

    if (
        "impersonate" not in done
        and not impersonated
        and has_impersonate_targets
        and (
            cat == IMPERSONATION_MISSING
            or looks_like_fingerprint(text)
        )
    ):
        return "impersonate"

    if (
        not (done & COOKIE_ATTEMPT_NAMES)
        and silent_cookies
        and should_try_silent_cookies(cat, text, url, attempts=attempts)
    ):
        return SILENT_FIREFOX_COOKIES

    if (
        cat in {BOT_CHECK, RATE_LIMITED}
        and BOT_RETRY not in done
        and not cookies_attempt_done(attempts)
    ):
        return BOT_RETRY

    if (
        "generic" not in done
        and cat not in SKIP_GENERIC_CATEGORIES
        and is_http_url(url)
        and looks_like_generic_mismatch(text)
    ):
        return "generic"

    return None


def recover_browser_cookies(
    url: str,
    *,
    importer: Any | None = None,
    browsers: tuple[str, ...] = AUTO_COOKIE_BROWSERS,
    probe: Any | None = None,
    repo: Any | None = None,
    timeout_sec: float | None = None,
    file_only: bool = False,
) -> dict[str, Any]:
    """Same core as fail-pause “Import from Firefox / browser”: import then validate.

    Worker-safe. Silent auto-recovery passes *timeout_sec* (default 60s total) and
    *file_only* so a hung yt-dlp/Firefox or live extract_info probe cannot block
    the sequential worker forever. Never arms the worker.
    """
    try:
        return _recover_browser_cookies(
            url,
            importer=importer,
            browsers=browsers,
            probe=probe,
            repo=repo,
            timeout_sec=timeout_sec,
            file_only=file_only,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("cookie recovery failed for %s", url)
        return {
            "ok": False,
            "stage": "error",
            "message": f"cookie recovery error: {exc}",
            "retried": False,
            "browsers": list(browsers),
        }


def _validate_after_import(
    url: str,
    *,
    probe: Any | None,
    file_only: bool,
) -> Any:
    from frameforge.download.cookie_validate import validate_cookies_for_url

    return validate_cookies_for_url(
        url,
        probe=None if file_only else probe,
        skip_probe_if_session=not file_only,
        file_only=file_only,
    )


def _recover_browser_cookies(
    url: str,
    *,
    importer: Any | None = None,
    browsers: tuple[str, ...] = AUTO_COOKIE_BROWSERS,
    probe: Any | None = None,
    repo: Any | None = None,
    timeout_sec: float | None = None,
    file_only: bool = False,
) -> dict[str, Any]:
    from frameforge.download.cookie_validate import (
        UNLOCK_FAIL,
        enable_gentle_after_bot,
        mark_cookies_validated,
    )

    def _finish_ok(browser: str, result: Any, validation: Any) -> dict[str, Any]:
        mark_cookies_validated(url)
        if repo is not None:
            try:
                enable_gentle_after_bot(repo)
            except Exception:  # noqa: BLE001
                pass
        return {
            "ok": True,
            "stage": "ready",
            "browser": browser,
            "result": result,
            "validation": validation,
            "message": (getattr(validation, "message", None) or "Cookies validated for this domain.")
            + " Retry this job and resume the queue.",
            "retried": False,
            "browsers": list(browsers),
        }

    if importer is not None:
        result = importer(url)
        ok = bool(result.get("ok") if isinstance(result, dict) else getattr(result, "ok", False))
        if not ok:
            msg = (
                result.get("message")
                if isinstance(result, dict)
                else getattr(result, "message", None)
            )
            return {
                "ok": False,
                "stage": "import",
                "message": msg or "Cookie import failed.",
                "result": result,
                "retried": False,
                "browser": "firefox",
                "browsers": ["injected"],
            }
        browser = "firefox"
        if isinstance(result, dict):
            browser = str(result.get("browser") or "firefox")
        else:
            browser = str(getattr(result, "browser", None) or "firefox")
        validation = _validate_after_import(url, probe=probe, file_only=file_only)
        if not validation.ok:
            return {
                "ok": False,
                "stage": "validate",
                "message": validation.message or UNLOCK_FAIL,
                "result": result,
                "validation": validation,
                "retried": False,
                "browser": browser,
            }
        return _finish_ok(browser, result, validation)

    from frameforge.download.browser_import import import_cookies_from_browser

    errors: list[str] = []
    last_result: Any = None
    timed_out = False
    deadline = None if timeout_sec is None else time.monotonic() + max(0.05, float(timeout_sec))
    budget = SILENT_IMPORT_TIMEOUT_SEC if timeout_sec is None else max(0.05, float(timeout_sec))
    for browser in browsers:
        remaining: float | None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.05:
                timed_out = True
                errors.append(f"timed out after {budget:.0f}s")
                break
        else:
            remaining = None
        imported = import_cookies_from_browser(
            url,
            browser=browser,
            timeout=remaining,
        )
        last_result = imported
        blob = str(imported.message or "")
        if "timed out" in blob.lower():
            timed_out = True
        if imported.ok:
            validation = _validate_after_import(url, probe=probe, file_only=file_only)
            if validation.ok:
                return _finish_ok(browser, imported, validation)
            errors.append(f"{browser}: imported but validate failed ({validation.message})")
        else:
            errors.append(f"{browser}: {imported.message}")
            if timed_out and deadline is not None and (deadline - time.monotonic()) <= 1.0:
                break
    return {
        "ok": False,
        "stage": "timeout" if timed_out else "import",
        "message": " | ".join(errors) or "Cookie import failed.",
        "result": last_result,
        "retried": False,
        "browsers": list(browsers),
    }


def silent_cookie_import(
    url: str,
    *,
    importer: Any | None = None,
    timeout_sec: float = SILENT_IMPORT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Firefox then Edge, once each. File-only validate; hard timeout. Never blocks forever."""
    try:
        if importer is not None:
            result = importer(url)
            ok = bool(result.get("ok") if isinstance(result, dict) else getattr(result, "ok", False))
            browser = None
            if isinstance(result, dict):
                browser = result.get("browser")
            else:
                browser = getattr(result, "browser", None)
            return {
                "ok": ok,
                "result": result,
                "browser": browser or "firefox",
                "browsers": ["injected"],
            }
        from frameforge.download.cookie_validate import cookies_validated_in_session
        from frameforge.download.cookies import has_cookies

        if has_cookies(url) and cookies_validated_in_session(url):
            return {
                "ok": True,
                "browser": "existing",
                "skipped_import": True,
                "stage": "ready",
                "message": "Cookies already validated this session.",
                "retried": False,
            }
        return recover_browser_cookies(
            url,
            browsers=AUTO_COOKIE_BROWSERS,
            timeout_sec=timeout_sec,
            file_only=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("silent cookie import failed for %s", url)
        return {
            "ok": False,
            "stage": "error",
            "message": f"cookie recovery error: {exc}",
            "retried": False,
        }
