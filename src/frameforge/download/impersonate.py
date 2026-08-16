"""yt-dlp browser impersonation (curl_cffi) for PornHub / MindGeek hosts."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

PINNED_CURL_CFFI = "0.13.0"
# curl_cffi 0.16.x reports as unsupported with yt-dlp 2026.07.04 (no CurlCFFI handler).
# Do not upgrade curl_cffi alone to 0.16 without yt-dlp past ~2026.08.16.
CURL_CFFI_UNSUPPORTED_WITH_YTDLP_2026_07 = ("0.16",)

IMPERSONATE_SETTING = "impersonate_mode"
MODE_AUTO = "auto"
MODE_ALWAYS = "always"
MODE_OFF = "off"
MODES = (MODE_AUTO, MODE_ALWAYS, MODE_OFF)
DEFAULT_MODE = MODE_AUTO

# PornHub + related Aylo/MindGeek extractors that 410 without --impersonate.
_IMPERSONATE_HOSTS = (
    "pornhub.com",
    "pornhubpremium.com",
    "pornhub.org",
    "youporn.com",
    "redtube.com",
    "tube8.com",
)

_IMPERSONATE_EXTRACTOR_MARKERS = (
    "pornhub",
    "pornhubpremium",
    "youporn",
    "redtube",
    "tube8",
    "mindgeek",
)

IMPERSONATION_FIX = (
    f"Install curl_cffi=={PINNED_CURL_CFFI} in the FrameForge venv "
    f"(pip install curl_cffi=={PINNED_CURL_CFFI}), then run "
    "python -m frameforge --check-env and confirm Chrome is available. "
    "Do not upgrade curl_cffi to 0.16.x while yt-dlp is 2026.07.04."
)


def impersonate_mode(repo: Any | None = None, raw: str | None = None) -> str:
    if raw is None and repo is not None and hasattr(repo, "get_setting"):
        raw = str(repo.get_setting(IMPERSONATE_SETTING, DEFAULT_MODE) or DEFAULT_MODE)
    text = str(raw or DEFAULT_MODE).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return MODE_ALWAYS
    if text in {"0", "false", "no"}:
        return MODE_OFF
    return text if text in MODES else DEFAULT_MODE


def _host(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def url_needs_impersonate(url: str) -> bool:
    """True for PornHub / related MindGeek hosts (Settings Auto)."""
    host = _host(url)
    if host:
        for suffix in _IMPERSONATE_HOSTS:
            if host == suffix or host.endswith("." + suffix):
                return True
    lower = (url or "").lower()
    return any(marker in lower for marker in _IMPERSONATE_EXTRACTOR_MARKERS)


def adult_site_in_text(text: str | None) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _IMPERSONATE_EXTRACTOR_MARKERS)


def curl_cffi_version() -> str | None:
    try:
        import curl_cffi

        ver = getattr(curl_cffi, "__version__", None)
        return str(ver) if ver else None
    except Exception:  # noqa: BLE001
        return None


def curl_cffi_unsupported_version(version: str | None = None) -> bool:
    ver = version if version is not None else curl_cffi_version()
    if not ver:
        return False
    return any(str(ver).startswith(prefix) for prefix in CURL_CFFI_UNSUPPORTED_WITH_YTDLP_2026_07)


def list_impersonate_targets() -> list[str]:
    """Available impersonate client strings, or empty if curl_cffi/yt-dlp cannot impersonate."""
    if curl_cffi_version() is None:
        return []
    if curl_cffi_unsupported_version():
        return []
    try:
        from yt_dlp.networking._curlcffi import CurlCFFIRH

        return [str(t) for t in (getattr(CurlCFFIRH, "supported_targets", None) or ())]
    except Exception:  # noqa: BLE001
        return []


def chrome_target_available(targets: list[str] | None = None) -> bool:
    items = targets if targets is not None else list_impersonate_targets()
    return any(str(t).lower().startswith("chrome") for t in items)


def select_impersonate_client(targets: list[str] | None = None) -> str | None:
    """Best CLI value for --impersonate: chrome, else edge, else first client name."""
    items = targets if targets is not None else list_impersonate_targets()
    if not items:
        return None
    lower = [str(t).lower() for t in items]
    chrome_win = [t for t in lower if t.startswith("chrome") and "windows" in t]
    if chrome_win or any(t.startswith("chrome") for t in lower):
        return "chrome"
    edge_win = [t for t in lower if t.startswith("edge") and "windows" in t]
    if edge_win or any(t.startswith("edge") for t in lower):
        return "edge"
    first = str(items[0])
    client = first.split(":", 1)[0].split("-", 1)[0]
    return client or first


def should_impersonate(
    url: str,
    *,
    mode: str | None = None,
    repo: Any | None = None,
    targets: list[str] | None = None,
) -> bool:
    resolved = impersonate_mode(repo, mode)
    if resolved == MODE_OFF:
        return False
    items = targets if targets is not None else list_impersonate_targets()
    if not items:
        return False
    if resolved == MODE_ALWAYS:
        return True
    return url_needs_impersonate(url)


def impersonate_cli_args(
    url: str,
    *,
    mode: str | None = None,
    repo: Any | None = None,
    targets: list[str] | None = None,
) -> list[str]:
    if not should_impersonate(url, mode=mode, repo=repo, targets=targets):
        return []
    client = select_impersonate_client(targets if targets is not None else list_impersonate_targets())
    if not client:
        return []
    return ["--impersonate", client]


def impersonate_ydl_option(
    url: str,
    *,
    mode: str | None = None,
    repo: Any | None = None,
    targets: list[str] | None = None,
) -> Any | None:
    args = impersonate_cli_args(url, mode=mode, repo=repo, targets=targets)
    if len(args) < 2:
        return None
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget.from_str(args[1])
    except Exception:  # noqa: BLE001
        return args[1]


def missing_impersonation_error() -> str:
    ver = curl_cffi_version() or "(not installed)"
    return (
        "Impersonate target not available. "
        "no impersonate target / unsupported curl_cffi "
        f"(curl_cffi {ver}). PornHub and related sites need --impersonate chrome. "
        + IMPERSONATION_FIX
    )


def require_impersonate_for_url(url: str, *, repo: Any | None = None) -> str | None:
    """Return selected client, or raise when a PH-family URL cannot impersonate."""
    mode = impersonate_mode(repo)
    targets = list_impersonate_targets()
    client = select_impersonate_client(targets)
    if should_impersonate(url, mode=mode, repo=repo, targets=targets):
        return client
    if mode == MODE_OFF:
        return None
    if url_needs_impersonate(url) and not targets:
        raise RuntimeError(missing_impersonation_error())
    return client if url_needs_impersonate(url) else None


def impersonation_status() -> dict[str, Any]:
    from frameforge.download.invocation import bundled_yt_dlp_version

    ver = curl_cffi_version()
    targets = list_impersonate_targets()
    chrome = chrome_target_available(targets)
    client = select_impersonate_client(targets)
    unsupported = curl_cffi_unsupported_version(ver)
    if ver is None:
        error = f"curl_cffi not installed. pip install curl_cffi=={PINNED_CURL_CFFI}"
    elif unsupported:
        error = (
            f"curl_cffi {ver} is unsupported with yt-dlp 2026.07.04 "
            f"(no impersonate targets). Pin curl_cffi=={PINNED_CURL_CFFI}."
        )
    elif not chrome:
        error = (
            "Chrome impersonate target unavailable. "
            f"Install curl_cffi=={PINNED_CURL_CFFI} and re-run --check-env."
        )
    else:
        error = None
    ok = bool(chrome and not unsupported and ver)
    return {
        "ok": ok,
        "yt_dlp_version": bundled_yt_dlp_version(),
        "curl_cffi_version": ver,
        "curl_cffi_supported": bool(ver) and not unsupported and bool(targets),
        "chrome_available": chrome,
        "selected": client,
        "clients": targets,
        "pinned_curl_cffi": PINNED_CURL_CFFI,
        "error": error,
    }
