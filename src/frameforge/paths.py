"""Output path helpers for %USERPROFILE%\\Downloads\\FrameForge\\."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "FrameForge"
SUBDIRS = ("downloads", "upscaled", "temp", "models", "archive", "cookies", "thumbnails")


def user_downloads() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"


def frameforge_root() -> Path:
    return user_downloads() / APP_DIR_NAME


def downloads_dir() -> Path:
    return frameforge_root() / "downloads"


def upscaled_dir() -> Path:
    return frameforge_root() / "upscaled"


def temp_dir() -> Path:
    return frameforge_root() / "temp"


def models_dir() -> Path:
    return frameforge_root() / "models"


def archive_dir() -> Path:
    return frameforge_root() / "archive"


def cookies_dir() -> Path:
    return frameforge_root() / "cookies"


def thumbnails_dir() -> Path:
    return frameforge_root() / "thumbnails"


def db_path() -> Path:
    return frameforge_root() / "frameforge.db"


def ensure_output_tree() -> Path:
    root = frameforge_root()
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
