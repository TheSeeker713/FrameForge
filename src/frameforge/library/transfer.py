"""Same-drive move vs cross-drive copy2 → verify size → unlink source."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def volume_key(path: str | Path) -> str:
    """Drive letter or UNC share; used to decide copy vs rename."""
    drive, _ = os.path.splitdrive(str(Path(path)))
    return drive.lower()


def same_volume(src: str | Path, dest: str | Path) -> bool:
    a, b = volume_key(src), volume_key(dest)
    if a and b:
        return a == b
    try:
        return os.stat(src).st_dev == os.stat(Path(dest).parent if Path(dest).suffix else dest).st_dev
    except OSError:
        return a == b


def _copy_verify_unlink(src: Path, dest: Path) -> None:
    shutil.copy2(str(src), str(dest))
    try:
        src_size = src.stat().st_size
        dest_size = dest.stat().st_size
    except OSError as exc:
        raise OSError(f"Could not stat after copy {src} -> {dest}: {exc}") from exc
    if dest_size != src_size:
        try:
            dest.unlink()
        except OSError:
            log.warning("Left incomplete copy at %s (size %s vs %s)", dest, dest_size, src_size)
        raise OSError(f"Size mismatch after copy {src} -> {dest}: {dest_size} != {src_size}")
    src.unlink()


def transfer_file(src: str | Path, dest: str | Path) -> Path:
    """Place *src* at *dest*. Cross-volume uses copy2 + size check + unlink.

    Source unlink after a verified copy is the move completion, not a user delete.
    """
    src = Path(src)
    dest = Path(dest)
    if not src.is_file():
        raise FileNotFoundError(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and src.resolve() != dest.resolve():
        raise FileExistsError(dest)
    if src.resolve() == dest.resolve():
        return dest.resolve()
    if same_volume(src, dest):
        try:
            shutil.move(str(src), str(dest))
        except OSError as exc:
            log.info("rename failed (%s); falling back to copy2+verify+unlink", exc)
            _copy_verify_unlink(src, dest)
    else:
        _copy_verify_unlink(src, dest)
    if not dest.is_file():
        raise OSError(f"Transfer did not produce a file at {dest}")
    return dest.resolve()
