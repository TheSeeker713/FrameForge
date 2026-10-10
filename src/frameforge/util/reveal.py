"""Open containing folder / reveal file in Windows Explorer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from frameforge.db.repository import Job


class RevealError(ValueError):
    """Path missing or invalid for reveal/open-folder."""


def resolve_job_media_path(job: Job) -> Path:
    """Prefer output_path, then download_path. Raises RevealError if none usable."""
    for raw in (job.output_path, job.download_path):
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            return path.resolve()
    raise RevealError("No local file for this job (missing download_path/output_path)")


def containing_folder(path: Path) -> Path:
    path = Path(path)
    if path.is_dir():
        return path.resolve()
    if path.exists():
        return path.resolve().parent
    raise RevealError(f"Path does not exist: {path}")


def explorer_select_command(path: Path) -> list[str]:
    """Windows Explorer select. ``/select,`` is its own argument.

    Explorer often exits 1 after opening a window. Callers must not treat that as failure.
    """
    path = Path(path).resolve()
    return ["explorer", "/select,", str(path)]


def reveal_command(path: Path, *, platform: str | None = None) -> list[str]:
    """Argv that reveals a file. Tests pass ``platform`` and do not launch."""
    plat = platform or sys.platform
    target = Path(path)
    if plat == "win32":
        if target.is_dir():
            return ["explorer", str(target.resolve())]
        return explorer_select_command(target)
    resolved = str(target.resolve()) if target.exists() else str(target)
    if plat == "darwin":
        return ["open", "-R", resolved]
    folder = target if target.is_dir() else target.parent
    shown = str(folder.resolve()) if folder.exists() else str(folder)
    return ["xdg-open", shown]


def open_command(path: Path, *, platform: str | None = None) -> list[str]:
    """Argv that opens a file in the default app. Windows uses ``os.startfile``."""
    plat = platform or sys.platform
    target = Path(path)
    shown = str(target.resolve()) if target.exists() else str(target)
    if plat == "win32":
        return ["os.startfile", shown]
    if plat == "darwin":
        return ["open", shown]
    return ["xdg-open", shown]


def explorer_open_folder_command(folder: Path) -> list[str]:
    folder = Path(folder).resolve()
    return ["explorer", str(folder)]


def reveal_file(path: Path, *, launch: bool = True) -> Path:
    """Reveal *path* in Explorer (select file). Returns containing folder."""
    path = Path(path)
    if not path.exists():
        raise RevealError(f"Path does not exist: {path}")
    folder = containing_folder(path)
    if launch:
        # Do not wait. Explorer's exit code is not a failure.
        subprocess.Popen(reveal_command(path))  # noqa: S603
    return folder


def open_folder(path: Path, *, launch: bool = True) -> Path:
    """Open the containing folder for *path*. Returns the folder path."""
    folder = containing_folder(path)
    if launch:
        if sys.platform == "win32":
            subprocess.Popen(explorer_open_folder_command(folder))  # noqa: S603
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603
    return folder


def open_job_folder(job: Job, *, launch: bool = True) -> Path:
    return open_folder(resolve_job_media_path(job), launch=launch)


def reveal_job_file(job: Job, *, launch: bool = True) -> Path:
    return reveal_file(resolve_job_media_path(job), launch=launch)


def open_in_default_player(path: Path, *, launch: bool = True) -> Path:
    """Open a media file with the OS default app (`os.startfile` on Windows)."""
    path = Path(path)
    if not path.is_file():
        raise RevealError(f"Path does not exist: {path}")
    if launch and sys.platform == "win32":
        try:
            os.startfile(path)  # noqa: S606
        except OSError as exc:
            raise RevealError(f"Could not open {path}") from exc
    elif launch:
        subprocess.Popen(open_command(path))  # noqa: S603
    return path.resolve()
