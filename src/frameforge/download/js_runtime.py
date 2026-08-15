"""Detect Deno/Node for yt-dlp EJS (YouTube n/signature challenges)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

JS_RUNTIME_FIX = (
    "Install Deno from https://deno.land, then in the FrameForge venv run "
    'pip install -U "yt-dlp[default]" yt-dlp-ejs, and restart the app so the '
    "worker inherits PATH. FrameForge cannot solve YouTube n-challenges without a JS runtime."
)

_YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "youtu.be",
    "www.youtu.be",
)


def extra_tool_dirs() -> list[Path]:
    """Common install locations that a GUI-launched process may omit from PATH."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    pf = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    pf86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    user_local = Path(os.environ.get("USERPROFILE") or str(home)) / "AppData" / "Local"
    candidates = [
        home / ".deno" / "bin",
        home / ".cargo" / "bin",
        local / "deno",
        user_local / "deno",
        local / "Microsoft" / "WinGet" / "Links",
        pf / "nodejs",
        pf86 / "nodejs",
        pf / "Deno",
        home / "scoop" / "shims",
        home / "AppData" / "Roaming" / "npm",
    ]
    return [p for p in candidates if p.is_dir()]


def which_on_augmented_path(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    for folder in extra_tool_dirs():
        for exe in (name, f"{name}.exe", f"{name}.cmd"):
            cand = folder / exe
            if cand.is_file():
                return str(cand.resolve())
    return None


def detect_js_runtime() -> str | None:
    """Return 'deno', 'node', or None. Deno is preferred (yt-dlp default)."""
    if which_on_augmented_path("deno"):
        return "deno"
    if which_on_augmented_path("node"):
        return "node"
    return None


def js_runtime_path() -> str | None:
    runtime = detect_js_runtime()
    if runtime == "deno":
        return which_on_augmented_path("deno")
    if runtime == "node":
        return which_on_augmented_path("node")
    return None


def js_runtime_cli_args(runtime: str | None = None) -> list[str]:
    """Pass an explicit runtime so a GUI-launched worker does not miss Deno."""
    name = detect_js_runtime() if runtime is None else runtime
    if name == "deno":
        path = which_on_augmented_path("deno")
        spec = f"deno:{path}" if path else "deno"
        return ["--js-runtimes", spec]
    if name == "node":
        path = which_on_augmented_path("node")
        spec = f"node:{path}" if path else "node"
        return ["--js-runtimes", spec]
    return []


def url_needs_js_runtime(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in _YOUTUBE_HOSTS:
        return True
    if host.endswith(".youtube.com") or host.endswith(".youtu.be"):
        return True
    lower = (url or "").lower()
    return "youtube.com/" in lower or "youtu.be/" in lower


def missing_js_runtime_error() -> str:
    return (
        "n challenge solving failed: no JS runtime on PATH. "
        "YouTube returned only images / requested format not available without Deno or Node. "
        + JS_RUNTIME_FIX
    )


def require_js_runtime_for_url(url: str) -> str | None:
    """Return detected runtime, or raise RuntimeError for YouTube without Deno/Node."""
    runtime = detect_js_runtime()
    if runtime:
        return runtime
    if url_needs_js_runtime(url):
        raise RuntimeError(missing_js_runtime_error())
    return None


def js_runtime_status() -> dict[str, Any]:
    runtime = detect_js_runtime()
    path = js_runtime_path()
    return {
        "runtime": runtime,
        "path": path,
        "ok": runtime is not None,
        "tip": None
        if runtime
        else "Deno not found — YouTube downloads need Deno + yt-dlp-ejs. " + JS_RUNTIME_FIX,
    }
