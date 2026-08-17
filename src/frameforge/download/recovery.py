"""Automatic download recovery ladder (native, impersonate, cookies, generic)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from frameforge.errors import (
    AUTH_REQUIRED,
    BOT_CHECK,
    CANCELLED,
    DB_ERROR,
    DISK_SPACE,
    DRM_BLOCKED,
    IMPERSONATION_MISSING,
    JS_RUNTIME,
    NOT_AVAILABLE,
    OUTPUT_MISSING,
    classify_error,
)

SILENT_COOKIES_SETTING = "silent_browser_cookies"
GENERIC_EXTRACTORS_CLI = "generic,default"

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

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_fingerprint(message: str | None) -> bool:
    return bool(_FINGERPRINT_RE.search(str(message or "")))


def looks_like_generic_mismatch(message: str | None) -> bool:
    return bool(_GENERIC_MISMATCH_RE.search(str(message or "")))


def is_http_url(url: str | None) -> bool:
    text = str(url or "").strip()
    if _HTTP_URL_RE.match(text):
        return True
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def silent_cookies_enabled(repo: Any | None) -> bool:
    if repo is None or not hasattr(repo, "get_setting"):
        return True
    return str(repo.get_setting(SILENT_COOKIES_SETTING, "1") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def format_tried(attempts: list[str] | tuple[str, ...] | None) -> str:
    names = [str(a).strip() for a in (attempts or []) if str(a).strip()]
    if not names:
        return ""
    return "tried: " + ", ".join(names)


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
    """Return the next automatic step: impersonate | cookies | generic, or None.

    Order after the in-download aria2→native fallback:
    impersonate (fingerprint / impersonation_missing) → silent cookies → generic once.
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
        "cookies" not in done
        and silent_cookies
        and cat in {AUTH_REQUIRED, BOT_CHECK}
    ):
        return "cookies"

    if (
        "generic" not in done
        and cat not in SKIP_GENERIC_CATEGORIES
        and is_http_url(url)
        and looks_like_generic_mismatch(text)
    ):
        return "generic"

    return None


def silent_cookie_import(url: str, *, importer: Any | None = None) -> dict[str, Any]:
    """Firefox then Edge, once each. Never Chrome. Never loops. No GUI."""
    if importer is not None:
        result = importer(url)
        ok = bool(result.get("ok") if isinstance(result, dict) else getattr(result, "ok", False))
        return {"ok": ok, "result": result, "browsers": ["injected"]}
    from frameforge.download.browser_import import import_cookies_from_browser

    errors: list[str] = []
    for browser in ("firefox", "edge"):
        imported = import_cookies_from_browser(url, browser=browser)
        if imported.ok:
            from frameforge.download.cookie_validate import validate_cookies_for_url

            validation = validate_cookies_for_url(url, skip_probe_if_session=False)
            if validation.ok:
                return {"ok": True, "browser": browser, "validation": validation}
            errors.append(f"{browser}: imported but validate failed ({validation.message})")
        else:
            errors.append(f"{browser}: {imported.message}")
    return {"ok": False, "message": " | ".join(errors), "browsers": ["firefox", "edge"]}
