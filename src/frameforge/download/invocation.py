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


def _winget_gyan_ffmpeg() -> Path | None:
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    root = local / "Microsoft" / "WinGet" / "Packages"
    if not root.is_dir():
        return None
    found: list[Path] = []
    try:
        for pkg in root.glob("Gyan.FFmpeg*"):
            found.extend(p for p in pkg.glob("ffmpeg-*/bin/ffmpeg.exe") if p.is_file())
            found.extend(
                p
                for p in pkg.glob("**/ffmpeg.exe")
                if p.is_file() and p.parent.name.lower() == "bin"
            )
    except OSError:
        return None
    if not found:
        return None
    uniq = sorted({p.resolve() for p in found}, key=lambda p: p.stat().st_mtime, reverse=True)
    return uniq[0]


def _common_ffmpeg_candidates() -> list[Path]:
    pf = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    home = Path.home()
    choco = Path(os.environ.get("ChocolateyInstall") or r"C:\ProgramData\chocolatey")
    return [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        pf / "ffmpeg" / "bin" / "ffmpeg.exe",
        home / "scoop" / "shims" / "ffmpeg.exe",
        choco / "bin" / "ffmpeg.exe",
    ]


def ffmpeg_location() -> str | None:
    """PATH first, then WinGet Gyan.FFmpeg and other common Windows locations."""
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).resolve())
    gyan = _winget_gyan_ffmpeg()
    if gyan is not None:
        return str(gyan)
    for cand in _common_ffmpeg_candidates():
        if cand.is_file():
            return str(cand.resolve())
    return None


def ffprobe_location() -> str | None:
    exe = shutil.which("ffprobe")
    if exe:
        return str(Path(exe).resolve())
    ffmpeg = ffmpeg_location()
    if ffmpeg:
        sibling = Path(ffmpeg).with_name("ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe")
        if sibling.is_file():
            return str(sibling.resolve())
    return None


def download_subprocess_env() -> tuple[dict[str, str], dict[str, str]]:
    """Copy os.environ (never wipe PATH) and prepend ffmpeg/aria2c/Deno/Node dirs.

    Returns (env, overrides) where overrides are only the keys we changed.
    """
    from frameforge.download.js_runtime import extra_tool_dirs, which_on_augmented_path

    env = os.environ.copy()
    if not env.get("PATH"):
        env["PATH"] = os.environ.get("PATH", "")
    overrides: dict[str, str] = {}
    extra: list[str] = []
    ffmpeg = ffmpeg_location()
    if ffmpeg:
        extra.append(str(Path(ffmpeg).resolve().parent))
    probe = ffprobe_location()
    if probe:
        extra.append(str(Path(probe).resolve().parent))
    for tool in ("aria2c", "deno", "node"):
        loc = which_on_augmented_path(tool) if tool in {"deno", "node"} else shutil.which(tool)
        if loc:
            extra.append(str(Path(loc).resolve().parent))
    for folder in extra_tool_dirs():
        extra.append(str(folder))
    if extra:
        seen: list[str] = []
        for item in extra:
            if item not in seen:
                seen.append(item)
        old = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(seen + ([old] if old else []))
        overrides["PATH_prepend"] = os.pathsep.join(seen)
    runtime = None
    from frameforge.download.js_runtime import detect_js_runtime, js_runtime_path

    runtime = detect_js_runtime()
    if runtime:
        overrides["js_runtime"] = runtime
        path = js_runtime_path()
        if path:
            overrides["js_runtime_path"] = path
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
        "ffprobe_location": ffprobe_location() if ffmpeg else None,
        "js_runtime": (env_overrides or {}).get("js_runtime"),
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
