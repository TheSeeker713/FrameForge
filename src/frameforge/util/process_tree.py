"""Windows-friendly process tree helpers for hard cancel."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time


class DownloadCancelled(RuntimeError):
    """Raised when a download/upscale subprocess was terminated by cancel."""


class DownloadPaused(RuntimeError):
    """Raised when a download/upscale subprocess was stopped by pause (partials kept)."""


def popen_creationflags() -> int:
    """Flags so the child is a killable process-group root on Windows."""
    if sys.platform != "win32":
        return 0
    # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    return 0x00000200 | 0x08000000


def kill_process_tree(pid: int) -> None:
    """Force-kill a process and its descendants (yt-dlp/aria2c/ffmpeg)."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        return
    try:
        os.killpg(pid, 9)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, 9)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def pid_is_running(pid: int) -> bool:
    """Return True if *pid* still exists (best-effort on Windows)."""
    if pid is None or pid <= 0:
        return False
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return int(code.value) == 259  # STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def descendant_pids(pid: int) -> list[int]:
    """Child PIDs (flet.exe, yt-dlp, …). Empty if psutil is unavailable."""
    if pid <= 0:
        return []
    try:
        import psutil

        proc = psutil.Process(int(pid))
        return [int(c.pid) for c in proc.children(recursive=True)]
    except Exception:  # noqa: BLE001
        return []


def kill_gui_children(pid: int | None = None) -> list[int]:
    """Kill descendant processes first (flet HWND), never taskkill self first."""
    root = int(pid or os.getpid())
    kids = descendant_pids(root)
    for child in kids:
        try:
            kill_process_tree(child)
        except Exception:  # noqa: BLE001
            pass
    return kids


def force_kill_current_app() -> None:
    """Kill GUI children (flet.exe), then _exit this process. Last-resort quit."""
    try:
        kill_gui_children(os.getpid())
    except Exception:  # noqa: BLE001
        pass
    os._exit(1)


def wait_pid_gone(pid: int, timeout: float = 10.0) -> bool:
    """Wait until pid exits. Returns True if gone."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not pid_is_running(pid):
            return True
        time.sleep(0.05)
    return not pid_is_running(pid)
