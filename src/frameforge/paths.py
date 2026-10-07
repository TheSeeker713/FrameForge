"""Output path helpers for the FrameForge root.

App home (database, cookies, models, temp): ``FRAMEFORGE_ROOT``, then a
local root file when that folder already holds an install, then
``%USERPROFILE%\\Downloads\\FrameForge``.

Download folder: the first-run choice. Skip uses the Windows user folder.
Pytest redirects ``USERPROFILE`` and stays on that temp tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR_NAME = "FrameForge"
_ENV_MEDIA_ROOT = "FRAMEFORGE_ROOT"
# Captured at import, before a test redirects USERPROFILE.
_LAUNCH_USERPROFILE = os.environ.get("USERPROFILE")
# App infrastructure at the FrameForge root. Media lives under downloads/.
SUBDIRS = (
    "downloads",
    "temp",
    "models",
    "archive",
    "cookies",
    "thumbnails",
    "database",
    "metadata",
)
# Created under downloads/ — never as siblings of database/models.
DOWNLOAD_ASSET_SUBDIRS = (
    "upscaled",
    "converted",
)


def user_downloads() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"


def profile_frameforge_root() -> Path:
    """``%USERPROFILE%\\Downloads\\FrameForge`` — the Windows user default."""
    return user_downloads() / APP_DIR_NAME


def _appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME


def local_root_file() -> Path:
    """Existing app home (queue, cookies, models), outside the repo."""
    return _appdata_dir() / "root.txt"


def download_choice_file() -> Path:
    """Folder the user picked for new videos. Absent until onboarding answers."""
    return _appdata_dir() / "download_dir.txt"


def download_onboarded_file() -> Path:
    return _appdata_dir() / "download_onboarded.txt"


def _configured_root() -> Path | None:
    """Read the local root file. Ignored when pytest has redirected USERPROFILE."""
    if _userprofile_redirected():
        return None
    try:
        text = local_root_file().read_text(encoding="utf-8-sig").strip().strip('"')
    except OSError:
        return None
    if not text:
        return None
    candidate = Path(text)
    try:
        if candidate.is_dir():
            return candidate
    except OSError:
        return None
    return None


def frameforge_root() -> Path:
    """App home: database, cookies, models, and temp.

    A saved root file is an existing install's app home. It is not a
    network location and it is not the download folder.
    """
    override = os.environ.get(_ENV_MEDIA_ROOT, "").strip()
    if override:
        return Path(override)
    configured = _configured_root()
    if configured is not None:
        return configured
    return profile_frameforge_root()


def _userprofile_redirected() -> bool:
    """True when USERPROFILE was changed after import (pytest isolation)."""
    current = os.environ.get("USERPROFILE")
    if not _LAUNCH_USERPROFILE or not current:
        return False
    try:
        return Path(current).resolve() != Path(_LAUNCH_USERPROFILE).resolve()
    except OSError:
        return True


def media_root() -> Path:
    """App home. New videos use ``downloads_dir``, which may be another folder."""
    return frameforge_root()


_MIGRATED = False


def migrate_legacy_profile_root() -> None:
    """Copy database, models, and cookies off the profile Downloads folder once.

    Finished videos may already live on another volume. This brings the queue
    and weights with them. An explicit ``FRAMEFORGE_ROOT`` is left alone.
    """
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True
    if os.environ.get(_ENV_MEDIA_ROOT, "").strip():
        return
    dest_root = frameforge_root()
    src_root = profile_frameforge_root()
    try:
        if not src_root.is_dir() or src_root.resolve() == dest_root.resolve():
            return
    except OSError:
        return

    def _copy_files(src_dir: Path, dst_dir: Path, names: list[str] | None = None) -> None:
        if not src_dir.is_dir():
            return
        dst_dir.mkdir(parents=True, exist_ok=True)
        sources = [src_dir / name for name in names] if names is not None else list(src_dir.iterdir())
        for src in sources:
            if not src.is_file():
                continue
            dst = dst_dir / src.name
            if dst.exists():
                continue
            try:
                shutil.copy2(src, dst)
            except OSError:
                continue

    _copy_files(
        src_root / "database",
        dest_root / "database",
        ["frameforge.db", "frameforge.db-wal", "frameforge.db-shm"],
    )
    for sub in ("models", "cookies", "archive", "thumbnails", "metadata"):
        _copy_files(src_root / sub, dest_root / sub)


def download_scan_roots() -> list[Path]:
    """Folders the library should search for finished downloads.

    The app home is always included. A download folder that lives somewhere
    else is included too, so a first-run choice stays visible in the library.
    """
    candidates = [media_root(), frameforge_root()]
    downloads = downloads_dir()
    try:
        downloads.resolve().relative_to(frameforge_root().resolve())
    except (ValueError, OSError):
        candidates.append(downloads)
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    return roots


def download_staging_dir(output_dir: Path | None = None) -> Path:
    """In-flight yt-dlp parts, on the same volume as the finished file."""
    dest = temp_dir() / "dl"
    if output_dir is not None:
        try:
            Path(output_dir).resolve().relative_to(downloads_dir().resolve())
        except (ValueError, OSError):
            pass
        else:
            dest = downloads_dir().parent / "temp" / "dl"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _read_download_choice() -> Path | None:
    if _userprofile_redirected():
        return None
    try:
        text = download_choice_file().read_text(encoding="utf-8-sig").strip().strip('"')
    except OSError:
        return None
    if not text:
        return None
    return Path(text)


def download_location_chosen() -> bool:
    """True after the first-run download question is answered. Tests stay quiet."""
    if _userprofile_redirected():
        return True
    return download_onboarded_file().is_file()


def system_downloads_dir() -> Path:
    """Skip target: the Windows user's FrameForge downloads folder."""
    return profile_frameforge_root() / "downloads"


def _remember_download_dir(path: Path) -> Path:
    folder = _appdata_dir()
    folder.mkdir(parents=True, exist_ok=True)
    download_choice_file().write_text(str(path), encoding="utf-8")
    download_onboarded_file().write_text("1", encoding="utf-8")
    return path


def skip_download_location() -> Path:
    """Use the Windows user folder and remember that the question was answered."""
    dest = system_downloads_dir()
    dest.mkdir(parents=True, exist_ok=True)
    return _remember_download_dir(dest)


def choose_download_location(picked: str | Path) -> Path:
    """Put new videos under ``<picked>/FrameForge/downloads``.

    Picking a folder that is already named FrameForge uses that folder.
    """
    folder = Path(picked)
    home = folder if folder.name.lower() == APP_DIR_NAME.lower() else folder / APP_DIR_NAME
    dest = home / "downloads"
    dest.mkdir(parents=True, exist_ok=True)
    return _remember_download_dir(dest)


def downloads_dir() -> Path:
    """Where new videos are written. The app home can be a different folder."""
    saved = _read_download_choice()
    if saved is not None:
        return saved
    return frameforge_root() / "downloads"


def upscaled_dir() -> Path:
    return downloads_dir() / "upscaled"


def converted_dir() -> Path:
    return downloads_dir() / "converted"


def download_dir_for_site(site_key: str, category: str | None = None) -> Path:
    """New-job path: ``downloads/<bucket>/<category>/``.

    Adult sites use the ``porn`` bucket. Streaming sites use their site key
    (``youtube``, ``x.com``, …). ``category`` is the project heading folder.
    """
    from frameforge.paths_site import (
        DEFAULT_CATEGORY,
        download_bucket_for_site_key,
        sanitize_category,
    )

    bucket = download_bucket_for_site_key(site_key)
    cat = sanitize_category(category) if category else DEFAULT_CATEGORY
    return downloads_dir() / bucket / cat


def upscaled_dir_for_site(site_key: str) -> Path:
    from frameforge.paths_site import download_bucket_for_site_key

    return upscaled_dir() / download_bucket_for_site_key(site_key)


def converted_dir_for_site(site_key: str) -> Path:
    from frameforge.paths_site import download_bucket_for_site_key

    return converted_dir() / download_bucket_for_site_key(site_key)


def is_legacy_root_media_dir(path: Path | None) -> bool:
    """True when ``path`` is a former root-level site folder (not under downloads/)."""
    if path is None:
        return False
    try:
        resolved = Path(path).resolve()
        root = media_root().resolve()
    except OSError:
        return False
    if resolved.parent != root:
        return False
    name = resolved.name.lower()
    if name in {s.lower() for s in SUBDIRS} or name in {"upscaled", "converted", "videos", "library"}:
        return False
    return True


def _folder_has_inflight_parts(folder: Path) -> bool:
    try:
        return any(
            p.suffix.lower() in {".part", ".ytdl", ".aria2"} or ".part." in p.name.lower()
            for p in folder.rglob("*")
            if p.is_file()
        )
    except OSError:
        return True


def _merge_dir_into(src: Path, dest: Path) -> list[tuple[Path, Path]]:
    moved: list[tuple[Path, Path]] = []
    if not src.is_dir():
        return moved
    dest.mkdir(parents=True, exist_ok=True)
    try:
        for item in list(src.iterdir()):
            target = dest / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))
            moved.append((item, target))
        try:
            next(src.iterdir())
        except StopIteration:
            src.rmdir()
    except OSError:
        return moved
    return moved


def migrate_root_site_folders() -> list[tuple[Path, Path]]:
    """Move leftover root media folders into ``downloads/``."""
    from frameforge.paths_site import DEFAULT_CATEGORY, download_bucket_for_site_key

    root = media_root()
    if not root.is_dir():
        return []
    moved: list[tuple[Path, Path]] = []
    # Former root siblings that now live under downloads/.
    for name, dest in (
        ("upscaled", upscaled_dir()),
        ("converted", converted_dir()),
        ("videos", videos_dir()),
    ):
        src = root / name
        if src.is_dir() and not _folder_has_inflight_parts(src):
            moved.extend(_merge_dir_into(src, dest))

    skip = {s.lower() for s in SUBDIRS} | {"upscaled", "converted", "videos", "library"}
    for child in list(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.lower() in skip:
            continue
        if _folder_has_inflight_parts(child):
            continue
        bucket = download_bucket_for_site_key(child.name)
        dest = downloads_dir() / bucket / DEFAULT_CATEGORY
        moved.extend(_merge_dir_into(child, dest))
    return moved


def temp_dir() -> Path:
    return frameforge_root() / "temp"


def models_dir() -> Path:
    migrate_legacy_profile_root()
    return frameforge_root() / "models"


def archive_dir() -> Path:
    return frameforge_root() / "archive"


def cookies_dir() -> Path:
    migrate_legacy_profile_root()
    return frameforge_root() / "cookies"


def database_dir() -> Path:
    return frameforge_root() / "database"


def videos_dir() -> Path:
    """Loose videos collected by folder repair (under downloads/)."""
    return downloads_dir() / "videos"


def thumbnails_dir() -> Path:
    return frameforge_root() / "thumbnails"


def metadata_dir() -> Path:
    return frameforge_root() / "metadata"


def junk_dir() -> Path:
    return temp_dir() / "junk"


def db_path() -> Path:
    migrate_legacy_profile_root()
    return database_dir() / "frameforge.db"


def restrict_dir_to_current_user(folder: Path) -> None:
    """On Windows, leave only the current user with access. No shell theme changes."""
    if sys.platform != "win32" or _userprofile_redirected():
        return
    if not folder.is_dir():
        return
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["icacls", str(folder), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
        check=False,
        capture_output=True,
        creationflags=flags,
    )


def ensure_output_tree() -> Path:
    from frameforge.layout import repair_frameforge_tree

    migrate_legacy_profile_root()
    root = frameforge_root()
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    restrict_dir_to_current_user(root / "cookies")
    restrict_dir_to_current_user(root / "database")
    dl = downloads_dir()
    dl.mkdir(parents=True, exist_ok=True)
    for name in DOWNLOAD_ASSET_SUBDIRS:
        (dl / name).mkdir(parents=True, exist_ok=True)
    media = media_root()
    try:
        separate_media = media.resolve() != root.resolve()
    except OSError:
        separate_media = True
    if separate_media:
        media.mkdir(parents=True, exist_ok=True)
        (media / "downloads").mkdir(parents=True, exist_ok=True)
        (media / "temp" / "dl").mkdir(parents=True, exist_ok=True)
    migrate_root_site_folders()
    repair_frameforge_tree(root, site_folders=False)
    return root
