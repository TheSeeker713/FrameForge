"""Export Netscape cookies via yt-dlp --cookies-from-browser (user-triggered)."""

from __future__ import annotations

import subprocess
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
CHROME_ABE_HINT = (
    "Chrome cookie import cannot be fixed by FrameForge: Chrome uses App-Bound Encryption "
    "(DPAPI). Prefer Firefox Import, or export a Netscape cookies.txt and import it here. "
    "Closing Chrome does not unlock App-Bound cookies."
)


def missing_browser_message(browser: str) -> str:
    title = (browser or "browser").strip().capitalize()
    return (
        f"{title} not found / profile locked — close {title} and retry, or export cookies.txt."
    )

Runner = Callable[[list[str]], tuple[int, str, str]]


@dataclass
class BrowserImportResult:
    ok: bool
    message: str
    path: Path | None = None
    browser: str | None = None


IMPORT_TIMEOUT_SEC = 120


def _default_runner(cmd: list[str], timeout: float = IMPORT_TIMEOUT_SEC) -> tuple[int, str, str]:
    """Run yt-dlp cookies-from-browser; kill the process tree if *timeout* elapses."""
    from frameforge.util.process_tree import kill_process_tree, popen_creationflags

    limit = max(0.05, float(timeout))
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = popen_creationflags()
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    try:
        out, err = proc.communicate(timeout=limit)
        return int(proc.returncode or 0), out or "", err or ""
    except subprocess.TimeoutExpired:
        kill_process_tree(int(proc.pid or 0))
        try:
            proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        return -1, "", f"cookie import timed out after {limit:.0f}s"


def _call_runner(run: Runner, cmd: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        return run(cmd, timeout=timeout)  # type: ignore[misc, call-arg]
    except TypeError:
        return run(cmd)


def _looks_like_abe(text: str) -> bool:
    lower = text.lower()
    return any(
        n in lower
        for n in ("app-bound", "app bound encryption", "dpapi", "failed to decrypt")
    )


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
    timeout: float | None = None,
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
    limit = IMPORT_TIMEOUT_SEC if timeout is None else max(0.05, float(timeout))
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
            rc, out, err = _call_runner(run, cmd, limit)
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
        if name == "chrome" and (_looks_like_abe(blob) or _looks_like_chromium_lock(blob)):
            hint = " " + CHROME_ABE_HINT
        elif name in CHROMIUM_BROWSERS and _looks_like_chromium_lock(blob):
            hint = " " + CHROMIUM_LOCK_HINT
        elif name in {"chrome", "edge", "firefox"}:
            hint = " " + missing_browser_message(name)
        detail = (err or out or f"exit {rc}").strip().splitlines()
        short = detail[-1] if detail else f"exit {rc}"
        errors.append(f"{name}: {short}{hint}")
    msg = "Could not import cookies from browser. " + " | ".join(errors)
    if "chrome" in " ".join(browsers) and CHROME_ABE_HINT not in msg and any(
        _looks_like_abe(e) for e in errors
    ):
        msg += " " + CHROME_ABE_HINT
    if any(b in CHROMIUM_BROWSERS for b in browsers) and CHROMIUM_LOCK_HINT not in msg and CHROME_ABE_HINT not in msg:
        if any("chrome" in e.lower() or "edge" in e.lower() or "brave" in e.lower() for e in errors):
            msg += " " + CHROMIUM_LOCK_HINT
    return BrowserImportResult(False, msg.strip())
