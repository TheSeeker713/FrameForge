"""Same-drive move vs cross-drive chunked copy → verify size → unlink source."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

COPY_CHUNK = 8 * 1024 * 1024
LOG_EVERY_BYTES = 64 * 1024 * 1024
PARTIAL_SUFFIX = ".ffpartial"


class TransferCancelled(Exception):
    """User cancelled during a chunked copy. Source is left intact."""


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


def _staging_path(dest: Path) -> Path:
    """Write beside dest with a non-video suffix so Uncategorized never indexes a partial."""
    return Path(str(dest) + PARTIAL_SUFFIX)


def _abandon_partial(stage: Path, dest: Path) -> Path | None:
    """Remove dest-side partial on cancel. Source file is left intact."""
    if not stage.exists():
        return None
    try:
        stage.unlink()
    except OSError:
        log.warning("Could not remove dest-side partial %s", stage)
        return stage
    return None


def _chunked_copy_file(
    src: Path,
    dest: Path,
    *,
    cancel: object | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    log_line: Callable[[str], None] | None = None,
    file_index: int | None = None,
    chunk_size: int = COPY_CHUNK,
) -> None:
    total = src.stat().st_size
    copied = 0
    last_log = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = file_index if file_index is not None else 0

    def _log(copied_now: int) -> None:
        msg = f"COPY #{n} bytes={copied_now}/{total}"
        if log_line is not None:
            log_line(msg)
        else:
            log.info("%s", msg)

    with src.open("rb") as inf, dest.open("wb") as out:
        while True:
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                raise TransferCancelled(f"cancelled during copy of {src}")
            buf = inf.read(max(1, int(chunk_size)))
            if not buf:
                break
            out.write(buf)
            copied += len(buf)
            if on_progress is not None:
                on_progress(copied, total)
            if copied - last_log >= LOG_EVERY_BYTES or copied == total:
                _log(copied)
                last_log = copied
    try:
        shutil.copystat(str(src), str(dest), follow_symlinks=True)
    except OSError:
        log.debug("copystat failed for %s -> %s", src, dest)


def _copy_verify_unlink(
    src: Path,
    dest: Path,
    *,
    cancel: object | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    log_line: Callable[[str], None] | None = None,
    file_index: int | None = None,
    chunk_size: int = COPY_CHUNK,
) -> None:
    stage = _staging_path(dest)
    try:
        _chunked_copy_file(
            src,
            stage,
            cancel=cancel,
            on_progress=on_progress,
            log_line=log_line,
            file_index=file_index,
            chunk_size=chunk_size,
        )
        try:
            src_size = src.stat().st_size
            dest_size = stage.stat().st_size
        except OSError as exc:
            _abandon_partial(stage, dest)
            raise OSError(f"Could not stat after copy {src} -> {dest}: {exc}") from exc
        if dest_size != src_size:
            _abandon_partial(stage, dest)
            raise OSError(f"Size mismatch after copy {src} -> {dest}: {dest_size} != {src_size}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if stage.resolve() != dest.resolve():
            if dest.exists():
                _abandon_partial(stage, dest)
                raise FileExistsError(dest)
            os.replace(str(stage), str(dest))
        src.unlink()
    except TransferCancelled:
        leftover = _abandon_partial(stage, dest)
        if leftover is not None:
            log.info("ABORT in-copy leftover=%s", leftover)
        else:
            log.info("ABORT in-copy dest_partial_removed=1")
        raise


def transfer_file(
    src: str | Path,
    dest: str | Path,
    *,
    cancel: object | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    log_line: Callable[[str], None] | None = None,
    file_index: int | None = None,
    chunk_size: int = COPY_CHUNK,
) -> Path:
    """Place *src* at *dest*. Cross-volume uses chunked copy + size check + unlink.

    Source unlink after a verified copy is the move completion, not a user delete.
    Cancel during copy leaves the source and does not write a finished dest.
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
    kwargs = {
        "cancel": cancel,
        "on_progress": on_progress,
        "log_line": log_line,
        "file_index": file_index,
        "chunk_size": chunk_size,
    }
    if same_volume(src, dest):
        try:
            shutil.move(str(src), str(dest))
        except OSError as exc:
            log.info("rename failed (%s); falling back to chunked copy+verify+unlink", exc)
            _copy_verify_unlink(src, dest, **kwargs)
    else:
        _copy_verify_unlink(src, dest, **kwargs)
    if not dest.is_file():
        raise OSError(f"Transfer did not produce a file at {dest}")
    return dest.resolve()
