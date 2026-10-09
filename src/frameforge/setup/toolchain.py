"""Install and refresh the tools a download needs.

yt-dlp, aria2, FFmpeg, and Deno each have more than one source. A failed
source is skipped and the next one is tried. First-run setup is skipped when
the jobs table already has history. Settings can ask for setup again.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

SETTING_ONBOARDED = "toolchain_onboarded"
SETTING_VERSIONS = "toolchain_versions"

YTDLP_SOURCES = (
    "https://pypi.org/pypi/yt-dlp/json",
    "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
)
ARIA2_SOURCES = (
    "https://api.github.com/repos/aria2/aria2/releases/latest",
    "https://github.com/aria2/aria2/releases/latest",
)
FFMPEG_SOURCES = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
)
DENO_SOURCES = (
    "https://api.github.com/repos/denoland/deno/releases/latest",
    "https://github.com/denoland/deno/releases/latest",
)

WHY = {
    "yt-dlp": "Sites reject downloaders older than 90 days.",
    "aria2c": "aria2 keeps a download moving when the built-in downloader stalls.",
    "ffmpeg": "FFmpeg merges the picture and the original audio.",
    "deno": "Deno solves the checks some sites put in front of a video.",
}


def version_tuple(text: str | None) -> tuple[int, ...]:
    nums = [int(part) for part in re.findall(r"\d+", text or "")]
    return tuple(nums[:4])


def is_newer(latest: str | None, installed: str | None) -> bool:
    if not latest:
        return False
    if not installed:
        return True
    new = version_tuple(latest)
    old = version_tuple(installed)
    if not new or not old:
        return latest.strip() != installed.strip()
    return new > old


def job_history_count(repo: Any) -> int:
    row = repo.conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()
    if row is None:
        return 0
    try:
        return int(row["c"])
    except (KeyError, TypeError, IndexError):
        return int(row[0])


def launch_mode(repo: Any) -> str:
    """``wizard`` on a first run with an empty queue. ``check`` when history exists."""
    if repo.get_setting(SETTING_ONBOARDED, "0") == "1":
        return "check"
    if job_history_count(repo) > 0:
        repo.set_setting(SETTING_ONBOARDED, "1")
        return "check"
    return "wizard"


def reset_onboarding(repo: Any) -> None:
    repo.set_setting(SETTING_ONBOARDED, "0")


def mark_onboarded(repo: Any) -> None:
    repo.set_setting(SETTING_ONBOARDED, "1")


def tool_root() -> Path:
    from frameforge.paths import frameforge_root

    path = frameforge_root() / "tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tool_dirs() -> list[Path]:
    from frameforge.paths import frameforge_root

    root = frameforge_root() / "tools"
    found: list[Path] = []
    for rel in ("ffmpeg/bin", "aria2", "deno"):
        folder = root / rel
        if folder.is_dir():
            found.append(folder)
    return found


def bundled_exe(name: str) -> Path | None:
    for folder in tool_dirs():
        for candidate in (folder / f"{name}.exe", folder / name):
            if candidate.is_file():
                return candidate
    return None


def _json_version(payload: dict[str, Any]) -> str | None:
    info = payload.get("info")
    if isinstance(info, dict) and info.get("version"):
        return str(info["version"])
    tag = payload.get("tag_name")
    if tag:
        return str(tag).lstrip("v")
    return None


def fetch_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "FrameForge", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{url} did not return an object")
    return data


def remote_versions(fetch: Callable[[str], dict[str, Any]] | None = None) -> dict[str, str | None]:
    """Latest version from the first source that answers. Missing tools stay None."""
    getter = fetch or fetch_json
    found: dict[str, str | None] = {}
    groups = {
        "yt-dlp": YTDLP_SOURCES,
        "aria2c": ARIA2_SOURCES,
        "deno": DENO_SOURCES,
    }
    for name, urls in groups.items():
        version = None
        for url in urls:
            try:
                version = _json_version(getter(url))
            except Exception:
                version = None
            if version:
                break
        found[name] = version
    found["ffmpeg"] = "bundled" if bundled_exe("ffmpeg") else None
    return found


def installed_versions() -> dict[str, str | None]:
    from frameforge.download.invocation import bundled_yt_dlp_version, clear_yt_dlp_version_cache

    clear_yt_dlp_version_cache()
    versions: dict[str, str | None] = {"yt-dlp": bundled_yt_dlp_version()}
    if versions["yt-dlp"] in {None, "", "unknown"}:
        versions["yt-dlp"] = None
    versions["aria2c"] = _program_version(["aria2c", "--version"])
    versions["ffmpeg"] = _program_version(["ffmpeg", "-version"])
    versions["deno"] = _program_version(["deno", "--version"])
    return versions


def _program_version(cmd: list[str]) -> str | None:
    from frameforge.download.invocation import aria2c_path, ffmpeg_location
    from frameforge.download.js_runtime import which_on_augmented_path

    name = cmd[0]
    if name == "aria2c":
        exe = aria2c_path()
    elif name == "ffmpeg":
        exe = ffmpeg_location()
    else:
        exe = which_on_augmented_path(name)
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=20, check=False)
    except Exception:
        return None
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return text.splitlines()[0] if text else None


def updates_needed(
    installed: dict[str, str | None],
    remote: dict[str, str | None],
) -> list[str]:
    needed: list[str] = []
    for name in ("yt-dlp", "aria2c", "ffmpeg", "deno"):
        have = installed.get(name)
        latest = remote.get(name)
        if name == "ffmpeg":
            if not have and not bundled_exe("ffmpeg"):
                needed.append(name)
            continue
        if is_newer(latest, have) or not have:
            needed.append(name)
    return needed


def notice_for(names: list[str], remote: dict[str, str | None] | None = None) -> str:
    if not names:
        return ""
    bits = []
    for name in names:
        why = WHY.get(name, "A download tool was updated.")
        latest = (remote or {}).get(name)
        if latest and name == "yt-dlp":
            bits.append(f"Updated yt-dlp to {latest}. {why}")
        else:
            bits.append(f"Updated {name}. {why}")
    return " ".join(bits)


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    return int(proc.returncode)


def install_yt_dlp(run: Callable[[list[str]], int] | None = None) -> None:
    runner = run or _run
    commands = [
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp>=2026.8.19", "yt-dlp-ejs"],
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "yt-dlp-ejs", "--index-url", "https://pypi.org/simple"],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "https://github.com/yt-dlp/yt-dlp/archive/refs/heads/master.zip",
        ],
    ]
    errors: list[str] = []
    for cmd in commands:
        try:
            if runner(cmd) == 0:
                from frameforge.download.invocation import clear_yt_dlp_version_cache

                clear_yt_dlp_version_cache()
                return
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            continue
        errors.append(" ".join(cmd))
    raise RuntimeError("yt-dlp could not be installed from PyPI or GitHub. " + "; ".join(errors[:3]))


def _download(url: str, dest: Path) -> None:
    request = Request(url, headers={"User-Agent": "FrameForge"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=120) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _extract_named(archive: Path, dest: Path, exe_name: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        member = None
        for info in bundle.infolist():
            if Path(info.filename).name.lower() == exe_name.lower():
                member = info
                break
        if member is None:
            raise FileNotFoundError(f"{exe_name} was not in {archive.name}")
        target = dest / exe_name
        with bundle.open(member) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)
    return target


def _first_zip(urls: tuple[str, ...], dest: Path, download: Callable[[str, Path], None]) -> None:
    errors: list[str] = []
    for url in urls:
        try:
            download(url, dest)
            if dest.is_file() and dest.stat().st_size > 0:
                return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
    raise RuntimeError("No download source answered. " + "; ".join(errors[:2]))


def install_aria2(download: Callable[[str, Path], None] | None = None) -> Path:
    getter = download or _download
    root = tool_root() / "aria2"
    archive = tool_root() / "aria2.zip"
    urls = _aria2_zip_urls()
    _first_zip(urls, archive, getter)
    exe = _extract_named(archive, root, "aria2c.exe")
    archive.unlink(missing_ok=True)
    return exe


def _aria2_zip_urls() -> tuple[str, ...]:
    version = None
    try:
        version = _json_version(fetch_json(ARIA2_SOURCES[0]))
    except Exception:
        version = None
    if not version:
        try:
            version = _json_version(fetch_json(ARIA2_SOURCES[1]))
        except Exception:
            version = None
    if not version:
        return (
            "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip",
        )
    tag = version if version.startswith("release-") else f"release-{version}"
    plain = version.removeprefix("release-")
    name = f"aria2-{plain}-win-64bit-build1.zip"
    return (
        f"https://github.com/aria2/aria2/releases/download/{tag}/{name}",
        f"https://github.com/aria2/aria2/releases/download/release-{plain}/{name}",
    )


def install_ffmpeg(download: Callable[[str, Path], None] | None = None) -> Path:
    getter = download or _download
    root = tool_root() / "ffmpeg" / "bin"
    archive = tool_root() / "ffmpeg.zip"
    _first_zip(FFMPEG_SOURCES, archive, getter)
    exe = _extract_named(archive, root, "ffmpeg.exe")
    try:
        _extract_named(archive, root, "ffprobe.exe")
    except FileNotFoundError:
        pass
    archive.unlink(missing_ok=True)
    return exe


def install_deno(download: Callable[[str, Path], None] | None = None) -> Path:
    getter = download or _download
    version = None
    for url in DENO_SOURCES:
        try:
            version = _json_version(fetch_json(url))
        except Exception:
            version = None
        if version:
            break
    root = tool_root() / "deno"
    archive = tool_root() / "deno.zip"
    if version:
        urls = (
            f"https://github.com/denoland/deno/releases/download/v{version.lstrip('v')}/deno-x86_64-pc-windows-msvc.zip",
            f"https://github.com/denoland/deno/releases/download/{version}/deno-x86_64-pc-windows-msvc.zip",
        )
    else:
        urls = ("https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",)
    _first_zip(urls, archive, getter)
    exe = _extract_named(archive, root, "deno.exe")
    archive.unlink(missing_ok=True)
    return exe


def apply_updates(
    names: list[str],
    *,
    run: Callable[[list[str]], int] | None = None,
    download: Callable[[str, Path], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[str]:
    """Install the named tools. Returns the ones that installed."""
    done: list[str] = []
    for name in names:
        if on_progress:
            on_progress(f"Installing {name}. {WHY.get(name, '')}")
        if name == "yt-dlp":
            install_yt_dlp(run)
        elif name == "aria2c":
            install_aria2(download)
        elif name == "ffmpeg":
            install_ffmpeg(download)
        elif name == "deno":
            install_deno(download)
        else:
            continue
        done.append(name)
    return done
