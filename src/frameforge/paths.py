"""Output path helpers — default root: K:\\JEREMY'S FILES\\downloads (Windows).

Root resolution order (first match wins):
  1. Config file  %APPDATA%\\FrameForge\\frameforge.cfg  →  media_root key
  2. Default:     K:\\JEREMY'S FILES\\downloads  (Windows)
                  ~/Downloads/FrameForge          (non-Windows)
  3. Fallback:    %USERPROFILE%\\Downloads\\FrameForge  when K: drive is absent

Users may change the root in Settings → Download Root at any time.
The choice is saved to the config file and does NOT touch SQLite.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR_NAME = "FrameForge"
SUBDIRS = (
    "downloads",
    "upscaled",
    "converted",
    "temp",
    "models",
    "archive",
    "cookies",
    "thumbnails",
    "database",
    "videos",
    "metadata",
)

# ---------------------------------------------------------------------------
# Platform defaults
# ---------------------------------------------------------------------------

WINDOWS_DEFAULT_ROOT: Path = Path(r"K:\JEREMY'S FILES\downloads")
_NON_WINDOWS_DEFAULT_ROOT: Path = Path.home() / "Downloads" / APP_DIR_NAME


def _non_windows_default() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads" / APP_DIR_NAME


def _platform_default() -> Path:
    if sys.platform == "win32":
        return WINDOWS_DEFAULT_ROOT
    return _non_windows_default()


# ---------------------------------------------------------------------------
# Config file (not SQLite — avoids circular bootstrap)
# ---------------------------------------------------------------------------

def _config_file() -> Path:
    """Fixed OS-level config file that survives across root moves."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME / "frameforge.cfg"


def get_configured_root() -> Path | None:
    """Return the user-saved root from the config file, or None if not set."""
    try:
        cfg = _config_file()
        if cfg.is_file():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            raw = data.get("media_root")
            if raw:
                return Path(raw)
    except Exception:  # noqa: BLE001
        pass
    return None


def set_media_root(path: str | Path) -> None:
    """Persist a user-chosen root to the config file.

    Call *invalidate_root_cache()* after this so ``frameforge_root()`` picks
    up the new value immediately.
    """
    cfg = _config_file()
    try:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {}
        data["media_root"] = str(Path(path).expanduser().resolve())
        cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        log.exception("Failed to write media root config to %s", cfg)


# ---------------------------------------------------------------------------
# Drive / root availability check
# ---------------------------------------------------------------------------

def _drive_accessible(path: Path) -> bool:
    """Return True if the drive (or mount point) of *path* is accessible."""
    try:
        drive_root = Path(path.drive + "\\") if path.drive else path.anchor
        if not drive_root or drive_root == path:
            return True
        return Path(drive_root).exists()
    except (OSError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# Root resolution with caching
# ---------------------------------------------------------------------------

_root_cache: tuple[Path, str | None] | None = None


def invalidate_root_cache() -> None:
    """Call after *set_media_root()* so the next call resolves the new path."""
    global _root_cache
    _root_cache = None


def _resolve_root() -> tuple[Path, str | None]:
    """Compute (root_path, optional_warning).  Does NOT create directories."""
    configured = get_configured_root()
    if configured is not None:
        return configured, None

    default = _platform_default()

    if sys.platform == "win32" and not _drive_accessible(default):
        fallback = _non_windows_default()
        warning = (
            f"Default media root {default} is unavailable "
            f"(drive not found or inaccessible). "
            f"Using fallback: {fallback}. "
            "You can change this in Settings → Download Root."
        )
        log.warning(warning)
        return fallback, warning

    return default, None


def _get_root() -> tuple[Path, str | None]:
    global _root_cache
    if _root_cache is None:
        _root_cache = _resolve_root()
    return _root_cache


def frameforge_root() -> Path:
    """Active FrameForge media root."""
    path, _ = _get_root()
    return path


def frameforge_root_warning() -> str | None:
    """Non-None warning string when the default root fell back due to missing drive."""
    _, warning = _get_root()
    return warning


# ---------------------------------------------------------------------------
# Subdirectory helpers (unchanged relative layout)
# ---------------------------------------------------------------------------

def user_downloads() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"


def downloads_dir() -> Path:
    return frameforge_root() / "downloads"


def upscaled_dir() -> Path:
    return frameforge_root() / "upscaled"


def converted_dir() -> Path:
    return frameforge_root() / "converted"


def download_dir_for_site(site_key: str) -> Path:
    """New-job download root: FrameForge/<site_key>/."""
    from frameforge.paths_site import sanitize_site_key

    return frameforge_root() / sanitize_site_key(site_key)


def upscaled_dir_for_site(site_key: str) -> Path:
    from frameforge.paths_site import sanitize_site_key

    return upscaled_dir() / sanitize_site_key(site_key)


def converted_dir_for_site(site_key: str) -> Path:
    from frameforge.paths_site import sanitize_site_key

    return converted_dir() / sanitize_site_key(site_key)


def temp_dir() -> Path:
    return frameforge_root() / "temp"


def models_dir() -> Path:
    return frameforge_root() / "models"


def archive_dir() -> Path:
    return frameforge_root() / "archive"


def cookies_dir() -> Path:
    return frameforge_root() / "cookies"


def database_dir() -> Path:
    return frameforge_root() / "database"


def videos_dir() -> Path:
    return frameforge_root() / "videos"


def thumbnails_dir() -> Path:
    return frameforge_root() / "thumbnails"


def metadata_dir() -> Path:
    return frameforge_root() / "metadata"


def junk_dir() -> Path:
    return temp_dir() / "junk"


def db_path() -> Path:
    return database_dir() / "frameforge.db"


def ensure_output_tree() -> Path:
    from frameforge.layout import repair_frameforge_tree

    root = frameforge_root()
    warning = frameforge_root_warning()
    if warning:
        log.warning("Media root warning: %s", warning)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("Cannot create media root %s: %s", root, exc)
        raise
    for name in SUBDIRS:
        try:
            (root / name).mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("Cannot create subdir %s under %s", name, root)
    repair_frameforge_tree(root, site_folders=False)
    return root
