"""Export Netscape cookies via yt-dlp --cookies-from-browser (user-triggered)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from frameforge.download.cookies import (
    cookie_path_for_domain,
    import_netscape_cookies,
    is_netscape_cookie_text,
    normalize_domain,
)

BROWSER_PREFERENCE = ("firefox", "edge", "chrome", "brave")
CHROMIUM_BROWSERS = frozenset({"edge", "chrome", "brave", "chromium", "opera", "vivaldi"})

CHROMIUM_LOCK_HINT = (
    "Chromium cookies may be locked (browser open) or App-Bound Encrypted. "
    "Close the browser and retry, use Firefox, or import a Netscape cookies.txt manually."
)

Runner = Callable[[list[str]], tuple[int, str, str]]


@dataclass
class BrowserImportResult:
    ok: bool
    message: str
    path: Path | None = None
    browser: str | None = None


def _default_runner(cmd: list[str]) -> tuple[int, str, str]:
    import subprocess

    proc = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""


def _looks_like_chromium_lock(text: str) -> bool:
    lower = text.lower()
    needles = (
        "could not copy",
        "failed to decrypt",
        "app-bound",
        "locked",
        "database is locked",
        "cookies.sqlite",
        "failed to load cookies",
        "dpapi",
    )
    return any(n in lower for n in needles)


def _build_cmd(browser: str, dest: Path, url: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yt_dlp",
        "--cookies-from-browser",
        browser,
        "--cookies",
        str(dest),
        "--skip-download",
        url,
    ]


def import_cookies_from_browser(
    url_or_domain: str,
    *,
    browser: str | None = None,
    runner: Runner | None = None,
) -> BrowserImportResult:
    """Run yt-dlp cookies-from-browser into FrameForge's per-domain Netscape store.

    *browser* None = try firefox, then edge, chrome, brave. User-triggered only.
    """
    try:
        domain = normalize_domain(url_or_domain)
    except ValueError as exc:
        return BrowserImportResult(False, str(exc))
    dest = cookie_path_for_domain(domain)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = url_or_domain.strip()
    if "://" not in url:
        url = f"https://{domain}/"
    browsers = [browser.strip().lower()] if browser else list(BROWSER_PREFERENCE)
    run = runner or _default_runner
    errors: list[str] = []
    for name in browsers:
        if not name:
            continue
        tmp = dest.with_name(dest.name + f".{name}.partial")
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        cmd = _build_cmd(name, tmp, url)
        try:
            rc, out, err = run(cmd)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            continue
        blob = f"{out}\n{err}"
        if tmp.is_file():
            text = tmp.read_text(encoding="utf-8", errors="ignore")
            if is_netscape_cookie_text(text):
                try:
                    saved = import_netscape_cookies(domain, tmp)
                except ValueError as exc:
                    errors.append(f"{name}: {exc}")
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                    continue
                try:
                    tmp.unlink()
                except OSError:
                    pass
                return BrowserImportResult(
                    True,
                    f"Imported cookies for {domain} from {name} → {saved}",
                    path=saved,
                    browser=name,
                )
            try:
                tmp.unlink()
            except OSError:
                pass
        hint = ""
        if name in CHROMIUM_BROWSERS and _looks_like_chromium_lock(blob):
            hint = " " + CHROMIUM_LOCK_HINT
        detail = (err or out or f"exit {rc}").strip().splitlines()
        short = detail[-1] if detail else f"exit {rc}"
        errors.append(f"{name}: {short}{hint}")
    msg = "Could not import cookies from browser. " + " | ".join(errors)
    if any(b in CHROMIUM_BROWSERS for b in browsers) and CHROMIUM_LOCK_HINT not in msg:
        if any("chrome" in e.lower() or "edge" in e.lower() or "brave" in e.lower() for e in errors):
            msg += " " + CHROMIUM_LOCK_HINT
    return BrowserImportResult(False, msg.strip())
