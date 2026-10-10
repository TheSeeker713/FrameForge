"""Send files to the Windows Recycle Bin (no Explorer theme changes)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


def recycle_flags() -> int:
    return FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI


def send_to_recycle_bin(path: str | Path, *, recycle: bool = True) -> None:
    """Move *path* to the Recycle Bin or Trash.

    ``recycle=False`` removes the file directly. Tests use that so a temp clip
    never lands in the real Recycle Bin. A failed recycle does not then delete
    the file.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not recycle:
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        else:
            target.unlink()
        return
    if sys.platform != "win32":
        _trash_posix(target)
        return
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    src = str(target.resolve()) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = src
    op.pTo = None
    op.fFlags = recycle_flags()
    op.fAnyOperationsAborted = False
    op.hNameMappings = None
    op.lpszProgressTitle = None
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0:
        raise OSError(f"SHFileOperationW failed ({rc}) for {target}")
    if target.exists():
        raise OSError(f"Recycle did not remove {target}")


def _trash_posix(target: Path) -> None:
    """macOS and Linux. A missing send2trash install is an error, not a delete."""
    try:
        from send2trash import send2trash
    except ImportError as exc:
        raise OSError("send2trash is not installed") from exc
    try:
        send2trash(str(target))
    except Exception as exc:
        raise OSError(f"Trash did not remove {target}") from exc
    if target.exists():
        raise OSError(f"Trash did not remove {target}")
