"""Output path helpers for %USERPROFILE%\\Downloads\\FrameForge\\."""

from __future__ import annotations

import os
from pathlib import Path

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
)


def user_downloads() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"


def frameforge_root() -> Path:
    return user_downloads() / APP_DIR_NAME


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


def db_path() -> Path:
    return database_dir() / "frameforge.db"


def ensure_output_tree() -> Path:
    from frameforge.layout import repair_frameforge_tree

    root = frameforge_root()
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    repair_frameforge_tree(root)
    return root
