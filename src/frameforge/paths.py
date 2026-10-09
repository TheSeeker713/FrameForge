"""Output path helpers for the FrameForge root.

App home (database, cookies, models, temp) follows the folder chosen in
onboarding. A custom pick keeps the whole tree under ``<picked>\\FrameForge``.
``%USERPROFILE%\\Downloads\\FrameForge`` is created only when onboarding
explicitly uses that Windows default (Skip).

``FRAMEFORGE_ROOT`` still overrides everything. Pytest redirects
``USERPROFILE`` and stays on that temp tree.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

APP_DIR_NAME = "FrameForge"
log = logging.getLogger(__name__)
_LIVE_FILE_SECONDS = 15 * 60
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


def _paths_equal(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _app_home_for_download_dir(choice: Path) -> Path:
    """``.../FrameForge/downloads`` → ``.../FrameForge``."""
    path = Path(choice)
    if path.name.lower() == "downloads":
        return path.parent
    return path


def _profile_tree_allowed() -> bool:
    """True when creating ``%USERPROFILE%\\Downloads\\FrameForge`` is intentional.

    That folder is the Windows default from onboarding Skip. A custom pick,
    and the time before any answer, must not create it. Pytest redirects
    ``USERPROFILE`` onto a temp tree and may use that temp default.
    """
    if os.environ.get(_ENV_MEDIA_ROOT, "").strip():
        return True
    if _userprofile_redirected():
        return True
    if not download_location_chosen():
        return False
    choice = _read_download_choice()
    if choice is None:
        return False
    return _paths_equal(_app_home_for_download_dir(choice), profile_frameforge_root())


def may_create(path: Path) -> bool:
    """False for ``%USERPROFILE%\\Downloads\\FrameForge`` unless that default was chosen."""
    profile = profile_frameforge_root()
    try:
        Path(path).resolve().relative_to(profile.resolve())
    except ValueError:
        return True
    except OSError:
        return True
    return _profile_tree_allowed()


def frameforge_root() -> Path:
    """App home: database, cookies, models, and temp.

    A custom download folder owns this home (its ``FrameForge`` parent).
    The Windows Downloads folder is used only after onboarding Skip.
    Before any answer, files stay under ``%APPDATA%\\FrameForge\\pending``.
    """
    override = os.environ.get(_ENV_MEDIA_ROOT, "").strip()
    if override:
        return Path(override)
    if _userprofile_redirected():
        return profile_frameforge_root()
    choice = _read_download_choice()
    if choice is not None and download_location_chosen():
        return _app_home_for_download_dir(choice)
    configured = _configured_root()
    if configured is not None and (
        not _paths_equal(configured, profile_frameforge_root()) or _profile_tree_allowed()
    ):
        return configured
    if _profile_tree_allowed():
        return profile_frameforge_root()
    return _appdata_dir() / "pending"


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
    if may_create(dest):
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


def _remember_app_home(home: Path) -> None:
    folder = _appdata_dir()
    folder.mkdir(parents=True, exist_ok=True)
    local_root_file().write_text(str(home), encoding="utf-8")


def _remember_download_dir(path: Path) -> Path:
    folder = _appdata_dir()
    folder.mkdir(parents=True, exist_ok=True)
    download_choice_file().write_text(str(path), encoding="utf-8")
    download_onboarded_file().write_text("1", encoding="utf-8")
    _remember_app_home(_app_home_for_download_dir(path))
    return path


def skip_download_location() -> Path:
    """Use the Windows user folder and remember that the question was answered.

    This is the only onboarding answer that creates
    ``%USERPROFILE%\\Downloads\\FrameForge``.
    """
    dest = system_downloads_dir()
    dest.mkdir(parents=True, exist_ok=True)
    return _remember_download_dir(dest)


def choose_download_location(picked: str | Path) -> Path:
    """Put the whole app tree under ``<picked>/FrameForge``.

    Picking a folder that is already named FrameForge uses that folder.
    Videos go in ``downloads/``. Database, cookies, models, and temp stay
    beside that folder. The Windows Downloads folder is not created.
    """
    folder = Path(picked)
    home = folder if folder.name.lower() == APP_DIR_NAME.lower() else folder / APP_DIR_NAME
    dest = home / "downloads"
    dest.mkdir(parents=True, exist_ok=True)
    return _remember_download_dir(dest)


def downloads_dir() -> Path:
    """Where new videos are written. Same FrameForge folder as the app home."""
    saved = _read_download_choice()
    if saved is not None:
        return saved
    return frameforge_root() / "downloads"


def upscaled_dir() -> Path:
    return downloads_dir() / "upscaled"


def converted_dir() -> Path:
    return downloads_dir() / "converted"


def download_dir_for_site(site_key: str, category: str | None = None) -> Path:
    """New-job path.

    Adult hosts use ``downloads/porn/<category>/``. YouTube, X, and Facebook
    use ``downloads/social/<platform>/<category>/``. Other hosts stay
    ``downloads/<host>/<category>/``.
    """
    from frameforge.paths_site import (
        DEFAULT_CATEGORY,
        SOCIAL_PLATFORM_KEYS,
        download_bucket_for_site_key,
        sanitize_category,
    )

    bucket = download_bucket_for_site_key(site_key)
    cat = sanitize_category(category) if category else DEFAULT_CATEGORY
    if bucket in SOCIAL_PLATFORM_KEYS:
        return downloads_dir() / "social" / bucket / cat
    return downloads_dir() / bucket / cat


def same_download_bucket(path: Path | None, expected: Path) -> bool:
    """True when ``path`` already sits in the same platform folder as ``expected``."""
    if path is None:
        return False
    try:
        resolved = Path(path).resolve()
        bucket = expected.resolve().parent
    except OSError:
        return False
    return resolved == bucket or resolved.parent == bucket or bucket in resolved.parents


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
    from frameforge.paths_site import DEFAULT_CATEGORY

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
        dest = download_dir_for_site(child.name, DEFAULT_CATEGORY)
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


def _file_is_live(path: Path) -> bool:
    """True for an in-flight part or a file the open download may still be writing."""
    name = path.name.lower()
    if path.suffix.lower() in {".part", ".ytdl", ".aria2"} or ".part." in name or name.endswith(".aria2"):
        return True
    try:
        return (time.time() - path.stat().st_mtime) < _LIVE_FILE_SECONDS
    except OSError:
        return True


def _prune_empty_dirs(folder: Path) -> None:
    if not folder.is_dir():
        return
    for child in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                continue
    try:
        folder.rmdir()
    except OSError:
        return


def _move_file_unique(src: Path, dest_dir: Path, *, respect_live: bool = True) -> Path | None:
    if not src.is_file() or (respect_live and _file_is_live(src)):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    try:
        if target.exists() and target.resolve() == src.resolve():
            return target
    except OSError:
        return None
    if target.exists():
        from frameforge.library.paths import unique_dest

        target = unique_dest(dest_dir, src.name)
    try:
        shutil.move(str(src), str(target))
    except OSError:
        log.exception("Could not move %s", src)
        return None
    return target


def place_finished_download(path: Path, *, site_key: str, category: str | None) -> Path:
    """Move a finished file into the bucket/category the app chose."""
    dest_dir = download_dir_for_site(site_key, category)
    try:
        if path.parent.resolve() == dest_dir.resolve():
            return path
    except OSError:
        pass
    moved = _move_file_unique(path, dest_dir, respect_live=False)
    return moved if moved is not None else path


def _routed_file_destination(downloads: Path, path: Path) -> Path | None:
    """Where a misplaced download file belongs. None when it is already right."""
    from frameforge.paths_site import (
        DEFAULT_CATEGORY,
        PORN_BUCKET,
        SOCIAL_PLATFORM_KEYS,
        category_from_metadata,
        download_bucket_for_site_key,
        facebook_id_in_name,
        title_from_media_name,
    )

    try:
        rel = path.resolve().relative_to(downloads.resolve())
    except (OSError, ValueError):
        return None
    if len(rel.parts) < 2:
        return None
    head = rel.parts[0].lower()
    if head in {"social", "converted", "upscaled", "videos"}:
        return None
    if facebook_id_in_name(path.name):
        cat = category_from_metadata(None, title=title_from_media_name(path.name))
        return downloads / "social" / "facebook" / cat / path.name
    if head == PORN_BUCKET:
        return None
    bucket = download_bucket_for_site_key(rel.parts[0])
    if bucket == PORN_BUCKET:
        rest = rel.parts[1:-1] or (DEFAULT_CATEGORY,)
        return downloads / PORN_BUCKET / Path(*rest) / path.name
    if bucket in SOCIAL_PLATFORM_KEYS or head in SOCIAL_PLATFORM_KEYS:
        platform = bucket if bucket in SOCIAL_PLATFORM_KEYS else head
        rest = rel.parts[1:-1] or (DEFAULT_CATEGORY,)
        return downloads / "social" / platform / Path(*rest) / path.name
    return None


def relocate_download_buckets() -> list[tuple[Path, Path]]:
    """Fold adult site folders into porn and social hosts under downloads/social.

    Skips a file the running download may still be writing. Does not delete media.
    """
    downloads = downloads_dir()
    if not downloads.is_dir():
        return []
    moved: list[tuple[Path, Path]] = []
    for child in list(downloads.iterdir()):
        if not child.is_dir():
            continue
        if child.name.lower() in {"social", "converted", "upscaled"}:
            continue
        if _folder_has_inflight_parts(child):
            continue
        for path in list(child.rglob("*")):
            if not path.is_file():
                continue
            dest = _routed_file_destination(downloads, path)
            if dest is None:
                continue
            try:
                if dest.resolve() == path.resolve():
                    continue
            except OSError:
                continue
            new_path = _move_file_unique(path, dest.parent)
            if new_path is not None and new_path.resolve() != path.resolve():
                moved.append((path, new_path))
        if child.name.lower() != "videos":
            _prune_empty_dirs(child)
    videos = downloads / "videos"
    if videos.is_dir() and not _folder_has_inflight_parts(videos):
        try:
            next(videos.rglob("*"))
        except StopIteration:
            try:
                videos.rmdir()
            except OSError:
                pass
        else:
            if not any(p.is_file() for p in videos.rglob("*")):
                _prune_empty_dirs(videos)
    _sync_download_paths(moved)
    return moved


def _existing_named_file(downloads: Path, name: str) -> Path | None:
    matches: list[Path] = []
    for bucket in (downloads / "social", downloads / "porn"):
        if not bucket.is_dir():
            continue
        matches.extend(p for p in bucket.rglob("*") if p.is_file() and p.name == name)
    if len(matches) == 1:
        return matches[0]
    return None


def _remap_dir_text(text: str) -> str:
    path = Path(text)
    parts = list(path.parts)
    try:
        idx = next(i for i, part in enumerate(parts) if part.lower() == "downloads")
    except StopIteration:
        return text
    if idx + 1 >= len(parts):
        return text
    head = parts[idx + 1]
    from frameforge.paths_site import (
        PORN_BUCKET,
        SOCIAL_PLATFORM_KEYS,
        category_from_metadata,
        download_bucket_for_site_key,
        facebook_id_in_name,
        title_from_media_name,
    )

    if facebook_id_in_name(path.name) and head.lower() != "social":
        found = _existing_named_file(Path(*parts[: idx + 1]), path.name)
        if found is not None:
            return str(found)
        cat = category_from_metadata(None, title=title_from_media_name(path.name))
        return str(Path(*parts[: idx + 1], "social", "facebook", cat, path.name))
    if head.lower() in {"social", "converted", "upscaled", "videos", "porn"}:
        return text
    bucket = download_bucket_for_site_key(head)
    rest = parts[idx + 2 :]
    if bucket == PORN_BUCKET or head.lower() == "eporner.com":
        parts = parts[: idx + 1] + [PORN_BUCKET, *rest]
    elif bucket in SOCIAL_PLATFORM_KEYS or head.lower() in SOCIAL_PLATFORM_KEYS:
        platform = bucket if bucket in SOCIAL_PLATFORM_KEYS else head.lower()
        parts = parts[: idx + 1] + ["social", platform, *rest]
    else:
        return text
    return str(Path(*parts))


def _sync_download_paths(moved: list[tuple[Path, Path]]) -> None:
    exact = {str(old): str(new) for old, new in moved}
    db = db_path()
    if not db.is_file() or not exact and not moved:
        if not db.is_file():
            return
    try:
        conn = sqlite3.connect(str(db), timeout=2)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        log.warning("Stored download paths were not rewritten; the database is locked")
        return

    def map_text(value: str | None) -> str | None:
        if not value:
            return value
        if value in exact:
            return exact[value]
        remapped = _remap_dir_text(value)
        return remapped if remapped != value else value

    try:
        rows = conn.execute("SELECT id, download_path, output_path, options_json FROM jobs").fetchall()
        for row in rows:
            download_path = map_text(row["download_path"])
            output_path = map_text(row["output_path"])
            raw = row["options_json"]
            new_raw = raw
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    changed = False
                    for key in ("download_output_dir",):
                        current = data.get(key)
                        if isinstance(current, str):
                            updated = map_text(current)
                            if updated and updated != current:
                                data[key] = updated
                                changed = True
                    if changed:
                        new_raw = json.dumps(data)
            if download_path != row["download_path"] or output_path != row["output_path"] or new_raw != raw:
                conn.execute(
                    "UPDATE jobs SET download_path = ?, output_path = ?, options_json = ? WHERE id = ?",
                    (download_path, output_path, new_raw, row["id"]),
                )
        try:
            lib_rows = conn.execute("SELECT id, path FROM library_items").fetchall()
        except sqlite3.Error:
            lib_rows = []
        for row in lib_rows:
            updated = map_text(row["path"])
            if updated and updated != row["path"]:
                conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (updated, row["id"]))
        try:
            archive_rows = conn.execute(
                "SELECT rowid AS archive_row, output_path FROM download_archive"
            ).fetchall()
        except sqlite3.Error:
            archive_rows = []
        for row in archive_rows:
            updated = map_text(row["output_path"])
            if updated and updated != row["output_path"]:
                conn.execute(
                    "UPDATE download_archive SET output_path = ? WHERE rowid = ?",
                    (updated, row["archive_row"]),
                )
        conn.commit()
    except (sqlite3.Error, KeyError, TypeError):
        log.warning("Stored download paths were not rewritten")
    finally:
        conn.close()


def ensure_output_tree() -> Path:
    from frameforge.layout import repair_frameforge_tree

    migrate_legacy_profile_root()
    root = frameforge_root()
    if may_create(root):
        root.mkdir(parents=True, exist_ok=True)
        for name in SUBDIRS:
            (root / name).mkdir(parents=True, exist_ok=True)
        restrict_dir_to_current_user(root / "cookies")
        restrict_dir_to_current_user(root / "database")
    dl = downloads_dir()
    if may_create(dl):
        dl.mkdir(parents=True, exist_ok=True)
        for name in DOWNLOAD_ASSET_SUBDIRS:
            (dl / name).mkdir(parents=True, exist_ok=True)
    media = media_root()
    try:
        separate_media = media.resolve() != root.resolve()
    except OSError:
        separate_media = True
    if separate_media and may_create(media):
        media.mkdir(parents=True, exist_ok=True)
        (media / "downloads").mkdir(parents=True, exist_ok=True)
        (media / "temp" / "dl").mkdir(parents=True, exist_ok=True)
    migrate_root_site_folders()
    relocate_download_buckets()
    repair_frameforge_tree(root, site_folders=False)
    return root
