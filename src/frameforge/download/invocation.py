"""Exact yt-dlp argv / env snapshot for CLI parity debugging."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_VERSION_CACHE: str | None = None
_PATH_YTDLP_CACHE: str | None = None
_PATH_YTDLP_PROBED = False


def bundled_yt_dlp_version() -> str:
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE
    try:
        from importlib.metadata import version

        _VERSION_CACHE = version("yt-dlp")
        return _VERSION_CACHE
    except Exception:  # noqa: BLE001
        pass
    try:
        from yt_dlp.version import __version__ as ver

        _VERSION_CACHE = str(ver)
        return _VERSION_CACHE
    except Exception:  # noqa: BLE001
        _VERSION_CACHE = "unknown"
        return _VERSION_CACHE


def path_yt_dlp_version() -> str | None:
    """Version of `yt-dlp` on PATH (the binary a terminal user typically runs)."""
    global _PATH_YTDLP_CACHE, _PATH_YTDLP_PROBED
    if _PATH_YTDLP_PROBED:
        return _PATH_YTDLP_CACHE
    _PATH_YTDLP_PROBED = True
    exe = shutil.which("yt-dlp")
    if not exe:
        _PATH_YTDLP_CACHE = None
        return None
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        _PATH_YTDLP_CACHE = (proc.stdout or proc.stderr or "").strip() or None
    except Exception:  # noqa: BLE001
        _PATH_YTDLP_CACHE = None
    return _PATH_YTDLP_CACHE


def aria2c_available() -> bool:
    return shutil.which("aria2c") is not None


def ffmpeg_location() -> str | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    return str(Path(exe).resolve())


def download_subprocess_env() -> tuple[dict[str, str], dict[str, str]]:
    """Copy os.environ and prepend directories of ffmpeg/aria2c if found.

    Returns (env, overrides) where overrides are only the keys we changed.
    """
    env = os.environ.copy()
    overrides: dict[str, str] = {}
    extra: list[str] = []
    for tool in ("ffmpeg", "ffprobe", "aria2c"):
        loc = shutil.which(tool)
        if loc:
            extra.append(str(Path(loc).resolve().parent))
    if extra:
        seen: list[str] = []
        for item in extra:
            if item not in seen:
                seen.append(item)
        old = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(seen + ([old] if old else []))
        overrides["PATH_prepend"] = os.pathsep.join(seen)
    return env, overrides


def snapshot_invocation(
    *,
    argv: list[str],
    cwd: str,
    output_template: str,
    cookies: str | None,
    aria2c: bool,
    format_selector: str,
    env_overrides: dict[str, str] | None = None,
    ffmpeg: str | None = None,
    returncode: int | None = None,
    stderr_empty: bool | None = None,
) -> dict[str, Any]:
    return {
        "argv": list(argv),
        "cwd": cwd,
        "output_template": output_template,
        "cookies": cookies,
        "aria2c": bool(aria2c),
        "format": format_selector,
        "env_overrides": dict(env_overrides or {}),
        "ffmpeg_location": ffmpeg,
        "yt_dlp_version": bundled_yt_dlp_version(),
        "yt_dlp_path_version": path_yt_dlp_version(),
        "python": sys.executable,
        "returncode": returncode,
        "stderr_empty": stderr_empty,
    }


def argv_summary(argv: list[str] | None) -> str:
    if not argv:
        return ""
    return subprocess.list2cmdline([str(a) for a in argv])
