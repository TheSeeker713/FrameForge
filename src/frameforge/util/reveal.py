"""Open containing folder / reveal file in Windows Explorer."""

from __future__ import annotations

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
    """Build the Windows Explorer /select command for a file."""
    path = Path(path).resolve()
    return ["explorer", f"/select,{path}"]


def explorer_open_folder_command(folder: Path) -> list[str]:
    folder = Path(folder).resolve()
    return ["explorer", str(folder)]


def reveal_file(path: Path, *, launch: bool = True) -> Path:
    """Reveal *path* in Explorer (select file). Returns containing folder."""
    path = Path(path)
    if not path.exists():
        raise RevealError(f"Path does not exist: {path}")
    folder = containing_folder(path)
    if launch and sys.platform == "win32":
        if path.is_file():
            subprocess.Popen(explorer_select_command(path))  # noqa: S603
        else:
            subprocess.Popen(explorer_open_folder_command(folder))  # noqa: S603
    elif launch:
        # Non-Windows fallback: open the folder
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603
    return folder


def open_folder(path: Path, *, launch: bool = True) -> Path:
    """Open the containing folder for *path*. Returns the folder path."""
    folder = containing_folder(path)
    if launch and sys.platform == "win32":
        subprocess.Popen(explorer_open_folder_command(folder))  # noqa: S603
    elif launch:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603
    return folder


def open_job_folder(job: Job, *, launch: bool = True) -> Path:
    return open_folder(resolve_job_media_path(job), launch=launch)


def reveal_job_file(job: Job, *, launch: bool = True) -> Path:
    return reveal_file(resolve_job_media_path(job), launch=launch)
