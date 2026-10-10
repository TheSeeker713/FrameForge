"""Put the library studio over the Library tab inside the FrameForge window.

The child window is created only for a FrameForge window whose process is this
one (or a child of it). Unknown handle, Explorer, or any other title: no-op.
This module does not read the foreground window and does not change desktop window attributes.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

from frameforge import __version__
from frameforge.ui_flet.library_studio import MARKER_RGB

log = logging.getLogger(__name__)

S_OK = 0
E_FAIL = 0x80004005
E_NOINTERFACE = 0x80004002
E_POINTER = 0x80004003
COINIT_APARTMENTTHREADED = 2
SW_HIDE = 0
SW_SHOW = 5
WM_SIZE = 5
WM_DESTROY = 2
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOP = 0
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

_IUNKNOWN = uuid.UUID("00000000-0000-0000-C000-000000000046")
_IID_ENV_DONE = "4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d"
_IID_CTRL_DONE = "6c4819f3-c9b7-4260-8127-c9f5bde7f68c"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetClientRect.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.RegisterClassW.restype = wintypes.ATOM
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.restype = ctypes.c_ssize_t

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.HRESULT
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.c_void_p,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ

_CLASS_ATOM = 0
_SURFACES: dict[int, "LibrarySurface"] = {}
_WNDPROC_REF: WNDPROC | None = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def shelf_screen_box(
    origin_x: int,
    origin_y: int,
    client_w: int,
    client_h: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    """Screen rect for the shelf, anchored to the bottom of the FrameForge client."""
    if client_w < 80 or client_h < 80:
        return None
    w = int(width) if width and width > 80 else int(client_w * 0.92)
    h = int(height) if height and height > 80 else int(client_h * 0.62)
    w = max(80, min(w, client_w - 8))
    h = max(80, min(h, client_h - 8))
    x = int(origin_x) + max(4, (client_w - w) // 2)
    y = int(origin_y) + max(4, client_h - h - 8)
    return (x, y, w, h)


user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ClientToScreen.restype = wintypes.BOOL


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


def _wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    if msg == WM_DESTROY:
        _SURFACES.pop(int(hwnd), None)
    return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))


def _ensure_class() -> None:
    global _CLASS_ATOM, _WNDPROC_REF
    if _CLASS_ATOM:
        return
    _WNDPROC_REF = WNDPROC(_wndproc)
    wc = WNDCLASSW()
    wc.lpfnWndProc = _WNDPROC_REF
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "FrameForgeLibraryShelf"
    wc.hbrBackground = gdi32.GetStockObject(4)  # BLACK_BRUSH
    atom = user32.RegisterClassW(ctypes.byref(wc))
    if not atom:
        err = ctypes.get_last_error()
        if err not in {1410}:  # class already exists
            raise OSError(f"RegisterClassW failed ({err})")
        atom = 1
    _CLASS_ATOM = int(atom)


def _window_title(hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _process_exe(pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def _parent_chain(pid: int) -> list[int]:
    TH32CS_SNAPPROCESS = 0x2
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if int(snap) in {0, -1}:
        return [pid]
    parents: dict[int, int] = {}
    try:
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    chain = [pid]
    seen = {pid}
    current = pid
    while current in parents and parents[current] not in seen and len(chain) < 8:
        current = parents[current]
        chain.append(current)
        seen.add(current)
    return chain


def frameforge_title() -> str:
    return f"FrameForge {__version__}"


def find_frameforge_hwnd(expected_title: str | None = None, our_pid: int | None = None) -> int | None:
    """HWND of this process's FrameForge window. None when it cannot be proved."""
    title = expected_title if expected_title is not None else frameforge_title()
    pid_self = os.getpid() if our_pid is None else int(our_pid)
    found: list[int] = []

    def visit(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if _window_title(int(hwnd)) != title:
            return True
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        exe = Path(_process_exe(int(proc.value))).name.lower()
        if exe != "flet.exe":
            return True
        chain = _parent_chain(int(proc.value))
        if pid_self not in chain and int(proc.value) != pid_self:
            return True
        found.append(int(hwnd))
        return True

    callback = WNDENUMPROC(visit)
    user32.EnumWindows(callback, 0)
    if len(found) != 1:
        return None
    return found[0]


def _is_marker(r: int, g: int, b: int) -> bool:
    mr, mg, mb = MARKER_RGB
    return abs(r - mr) <= 18 and abs(g - mg) <= 18 and abs(b - mb) <= 18


def marker_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Client rect of the solid shelf marker. None when the shelf is not on screen."""
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = int(rect.right), int(rect.bottom)
    if width < 40 or height < 40:
        return None
    hdc = user32.GetDC(hwnd)
    if not hdc:
        return None
    mem = gdi32.CreateCompatibleDC(hdc)
    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth = width
    info.biHeight = -height
    info.biPlanes = 1
    info.biBitCount = 32
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    if not hbmp or not bits.value:
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)
        return None
    gdi32.SelectObject(mem, hbmp)
    try:
        if not user32.PrintWindow(hwnd, mem, 2):
            return None
        buf = (ctypes.c_ubyte * (width * height * 4)).from_address(bits.value)
        min_run = max(120, int(width * 0.25))
        rows: list[tuple[int, int]] = []
        for y in range(height):
            best_x = 0
            best_len = 0
            run = 0
            run_start = 0
            row = y * width
            for x in range(width):
                i = (row + x) * 4
                if _is_marker(buf[i + 2], buf[i + 1], buf[i]):
                    if run == 0:
                        run_start = x
                    run += 1
                    if run > best_len:
                        best_len = run
                        best_x = run_start
                else:
                    run = 0
            rows.append((best_x, best_len))
        ys = [y for y, (_x, length) in enumerate(rows) if length >= min_run]
        if not ys:
            return None
        # Longest contiguous vertical span. Sparse black text does not qualify.
        start = ys[0]
        best = (ys[0], ys[0])
        prev = ys[0]
        for y in ys[1:]:
            if y == prev + 1:
                prev = y
                if prev - start > best[1] - best[0]:
                    best = (start, prev)
            else:
                start = y
                prev = y
        y0, y1 = best
        if y1 - y0 < 80:
            return None
        sample = rows[(y0 + y1) // 2]
        x, run = sample
        if run < min_run:
            return None
        if run * (y1 - y0 + 1) > int(width * height * 0.92):
            return None
        return (x, y0, run, y1 - y0 + 1)
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


def _slot(com: int, index: int) -> int:
    vtbl = ctypes.cast(com, ctypes.POINTER(ctypes.c_void_p))[0]
    return int(ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index])


def _call(com: int, index: int, proto: Any, *args: Any) -> int:
    fn = proto(_slot(com, index))
    hr = fn(com, *args)
    return int(hr) & 0xFFFFFFFF


def _addref(com: int) -> None:
    proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    proto(_slot(com, 1))(com)


def _release(com: int) -> None:
    if not com:
        return
    proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    proto(_slot(com, 2))(com)


class _Callback:
    def __init__(self, iid: str, on_invoke: Any) -> None:
        self.iid = uuid.UUID(iid)
        self.on_invoke = on_invoke
        self.ref = 1
        QI = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        AR = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        REL = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        INV = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.HRESULT, ctypes.c_void_p)

        def qi(this: int, riid: Any, ppv: Any) -> int:
            if not ppv:
                return E_POINTER
            raw = ctypes.string_at(ctypes.addressof(riid.contents), 16)
            want = uuid.UUID(bytes_le=raw)
            if want in {self.iid, _IUNKNOWN}:
                ppv[0] = this
                self.ref += 1
                return S_OK
            ppv[0] = None
            return E_NOINTERFACE

        def addref(_this: int) -> int:
            self.ref += 1
            return self.ref

        def release(_this: int) -> int:
            self.ref = max(0, self.ref - 1)
            return self.ref

        def invoke(_this: int, hr: int, ptr: int) -> int:
            try:
                self.on_invoke(int(hr) & 0xFFFFFFFF, int(ptr) if ptr else 0)
            except Exception:
                log.exception("WebView2 callback failed")
                return E_FAIL
            return S_OK

        self._fns = [QI(qi), AR(addref), REL(release), INV(invoke)]
        self._vt = (ctypes.c_void_p * 4)(*(ctypes.cast(fn, ctypes.c_void_p) for fn in self._fns))

        class _Obj(ctypes.Structure):
            _fields_ = [("lpVtbl", ctypes.POINTER(ctypes.c_void_p))]

        self._obj = _Obj(ctypes.cast(self._vt, ctypes.POINTER(ctypes.c_void_p)))

    def pointer(self) -> int:
        return ctypes.addressof(self._obj)


class LibrarySurface:
    """WebView2 child hosted on the FrameForge window's library shelf."""

    def __init__(self) -> None:
        self._cmds: list[tuple[Any, ...]] = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._child: int = 0
        self._parent: int = 0
        self._overlay: int = 0
        self._owner: int = 0
        self._want_visible = False
        self._overlay_url = ""
        self._size = (0, 0)
        self._env_started = False
        self._controller: int = 0
        self._webview: int = 0
        self._env: int = 0
        self._url = ""
        self._pending_url = ""
        self._owned_parent = 0
        self.last_error = ""
        self.ready = threading.Event()
        self._callbacks: list[_Callback] = []
        self._loader: Any = None

    def sync(self, *, url: str, visible: bool, width: int = 0, height: int = 0) -> None:
        self._start()
        with self._lock:
            self._cmds.append(("sync", url, bool(visible), int(width or 0), int(height or 0)))
        self._wake.set()

    def probe_offscreen(self, url: str, timeout: float = 20.0) -> bool:
        """Load the studio in a window this process owns, off the desktop."""
        self.ready.clear()
        self.last_error = ""
        self._start()
        with self._lock:
            self._cmds.append(("probe", url))
        self._wake.set()
        return self.ready.wait(timeout) and not self.last_error

    def embed_into(self, parent: int, url: str, timeout: float = 20.0) -> bool:
        """Host the studio as a child of an existing window. Used to prove cross-process parenting."""
        self.ready.clear()
        self.last_error = ""
        self._start()
        with self._lock:
            self._cmds.append(("into", int(parent), url))
        self._wake.set()
        return self.ready.wait(timeout) and not self.last_error

    def close(self) -> None:
        thread = self._thread
        if thread is None:
            return
        with self._lock:
            self._cmds.append(("close",))
        self._wake.set()
        if threading.current_thread() is not thread:
            thread.join(timeout=4)
        self._thread = None

    def _start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="library-studio-surface", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        try:
            _ensure_class()
            self._pump()
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Library surface stopped")
            self.ready.set()
        finally:
            self._teardown()
            ole32.CoUninitialize()

    def _peek(self) -> None:
        msg = MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _pump(self) -> None:
        while True:
            self._peek()
            with self._lock:
                cmds = self._cmds
                self._cmds = []
            if not cmds:
                self._wake.wait(0.2)
                self._wake.clear()
            elif self._dispatch(cmds):
                return
            if self._want_visible:
                self._place_overlay()

    def _dispatch(self, cmds: list[tuple[Any, ...]]) -> bool:
        for cmd in cmds:
            if cmd[0] == "close":
                return True
            if cmd[0] == "probe":
                self._probe(str(cmd[1]))
            elif cmd[0] == "into":
                self._embed(int(cmd[1]), (8, 8, 640, 360), str(cmd[2]))
            elif cmd[0] == "sync":
                width = int(cmd[3]) if len(cmd) > 3 else 0
                height = int(cmd[4]) if len(cmd) > 4 else 0
                self._sync(str(cmd[1]), bool(cmd[2]), width, height)
        return False

    def _probe(self, url: str) -> None:
        parent = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            "FrameForgeLibraryShelf",
            "FrameForgeLibraryShelfProbe",
            WS_POPUP,
            -3200,
            -3200,
            960,
            540,
            None,
            None,
            kernel32.GetModuleHandleW(None),
            None,
        )
        if not parent:
            self.last_error = f"probe window failed ({ctypes.get_last_error()})"
            self.ready.set()
            return
        self._owned_parent = int(parent)
        user32.ShowWindow(parent, SW_SHOW)
        self._embed(int(parent), (0, 0, 960, 540), url)

    def _sync(self, url: str, visible: bool, width: int = 0, height: int = 0) -> None:
        self._want_visible = bool(visible and url)
        self._overlay_url = url
        self._size = (int(width or 0), int(height or 0))
        if not self._want_visible:
            self._hide_overlay()
            return
        self._place_overlay()

    def _overlay_rect(self, owner: int) -> tuple[int, int, int, int] | None:
        client = RECT()
        if not user32.GetClientRect(owner, ctypes.byref(client)):
            return None
        origin = POINT(0, 0)
        if not user32.ClientToScreen(owner, ctypes.byref(origin)):
            return None
        return shelf_screen_box(
            int(origin.x),
            int(origin.y),
            int(client.right),
            int(client.bottom),
            self._size[0],
            self._size[1],
        )

    def _hide_overlay(self) -> None:
        self._hide()
        if self._overlay and user32.IsWindow(self._overlay):
            user32.ShowWindow(self._overlay, SW_HIDE)

    def _place_overlay(self) -> None:
        if not self._want_visible or not self._overlay_url:
            self._hide_overlay()
            return
        owner = find_frameforge_hwnd()
        if owner is None or not user32.IsWindowVisible(owner):
            self._hide_overlay()
            return
        rect = self._overlay_rect(owner)
        if rect is None:
            self._hide_overlay()
            return
        x, y, w, h = rect
        if not (self._overlay and user32.IsWindow(self._overlay)):
            overlay = user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,
                "FrameForgeLibraryShelf",
                "FrameForge Library",
                WS_POPUP | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                x,
                y,
                w,
                h,
                owner,
                None,
                kernel32.GetModuleHandleW(None),
                None,
            )
            if not overlay:
                self.last_error = f"library shelf window failed ({ctypes.get_last_error()})"
                log.warning(self.last_error)
                return
            self._overlay = int(overlay)
            self._owner = int(owner)
            _SURFACES[self._overlay] = self
            self._env_started = False
            self._destroy_webview()
        else:
            user32.SetWindowPos(self._overlay, HWND_TOP, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        user32.ShowWindow(self._overlay, SW_SHOW)
        self._child = self._overlay
        self._parent = self._overlay
        self._pending_url = self._overlay_url
        if self._webview:
            self._fit_and_navigate()
            return
        if self._env:
            if not self._controller:
                self._create_controller()
            return
        if not self._env_started:
            self._env_started = True
            self._create_environment()

    def _destroy_webview(self) -> None:
        controller = self._controller
        webview = self._webview
        env = self._env
        self._controller = 0
        self._webview = 0
        self._env = 0
        if controller:
            proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
            _call(controller, 24, proto)
            _release(webview)
            _release(controller)
        _release(env)

    def _hide(self) -> None:
        if self._child and user32.IsWindow(self._child):
            user32.ShowWindow(self._child, SW_HIDE)
        if self._controller:
            proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int)
            _call(self._controller, 4, proto, 0)

    def _embed(self, parent: int, rect: tuple[int, int, int, int], url: str) -> None:
        x, y, w, h = rect
        if self._child and self._parent == parent and user32.IsWindow(self._child):
            user32.SetWindowPos(self._child, HWND_TOP, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        else:
            self._destroy_child()
            child = user32.CreateWindowExW(
                0,
                "FrameForgeLibraryShelf",
                "",
                WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
                x,
                y,
                w,
                h,
                parent,
                None,
                kernel32.GetModuleHandleW(None),
                None,
            )
            if not child:
                self.last_error = f"shelf child failed ({ctypes.get_last_error()})"
                log.warning(self.last_error)
                self.ready.set()
                return
            self._child = int(child)
            self._parent = int(parent)
            _SURFACES[self._child] = self
            user32.SetWindowPos(self._child, HWND_TOP, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        user32.ShowWindow(self._child, SW_SHOW)
        self._pending_url = url
        if self._webview:
            self._fit_and_navigate()
            return
        if self._env:
            return
        self._create_environment()

    def _loader_dll(self) -> Any:
        if self._loader is not None:
            return self._loader
        path = Path(__file__).resolve().parent / "resources" / "WebView2Loader.dll"
        if not path.is_file():
            raise FileNotFoundError(path)
        self._loader = ctypes.WinDLL(str(path))
        return self._loader

    def _create_environment(self) -> None:
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FrameForge" / "library-webview"
        folder.mkdir(parents=True, exist_ok=True)

        def done(hr: int, env: int) -> None:
            if hr != S_OK or not env:
                self.last_error = f"WebView2 environment {hr:#x}"
                log.warning(self.last_error)
                self.ready.set()
                return
            _addref(env)
            self._env = env
            self._create_controller()

        callback = _Callback(_IID_ENV_DONE, done)
        self._callbacks.append(callback)
        create = self._loader_dll().CreateCoreWebView2EnvironmentWithOptions
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p]
        create.restype = ctypes.HRESULT
        hr = int(create(None, str(folder), None, ctypes.c_void_p(callback.pointer()))) & 0xFFFFFFFF
        if hr != S_OK:
            self.last_error = f"CreateCoreWebView2EnvironmentWithOptions {hr:#x}"
            log.warning(self.last_error)
            self.ready.set()

    def _create_controller(self) -> None:
        def done(hr: int, controller: int) -> None:
            if hr != S_OK or not controller:
                self.last_error = f"WebView2 controller {hr:#x}"
                log.warning(self.last_error)
                self.ready.set()
                return
            _addref(controller)
            self._controller = controller
            web = ctypes.c_void_p()
            proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
            got = _call(controller, 25, proto, ctypes.byref(web))
            if got != S_OK or not web.value:
                self.last_error = f"CoreWebView2 {got:#x}"
                self.ready.set()
                return
            self._webview = int(web.value)
            self._fit_and_navigate()

        callback = _Callback(_IID_CTRL_DONE, done)
        self._callbacks.append(callback)
        proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, ctypes.c_void_p)
        hr = _call(self._env, 3, proto, wintypes.HWND(self._child), ctypes.c_void_p(callback.pointer()))
        if hr != S_OK:
            self.last_error = f"CreateCoreWebView2Controller {hr:#x}"
            log.warning(self.last_error)
            self.ready.set()

    def _fit_and_navigate(self) -> None:
        if not self._controller or not self._child:
            return
        bounds = RECT()
        user32.GetClientRect(self._child, ctypes.byref(bounds))
        # x64 COM passes a 16-byte RECT as a pointer.
        proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(RECT))
        _call(self._controller, 6, proto, ctypes.byref(bounds))
        show = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int)
        _call(self._controller, 4, show, 1)
        if self._webview and self._pending_url and self._pending_url != self._url:
            nav = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p)
            hr = _call(self._webview, 5, nav, self._pending_url)
            if hr != S_OK:
                self.last_error = f"Navigate {hr:#x}"
                log.warning(self.last_error)
            else:
                self._url = self._pending_url
                self.last_error = ""
            self.ready.set()

    def _destroy_child(self) -> None:
        controller = self._controller
        webview = self._webview
        env = self._env
        self._controller = 0
        self._webview = 0
        self._env = 0
        if controller:
            proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
            _call(controller, 24, proto)
            _release(webview)
            _release(controller)
        _release(env)
        child = self._child
        overlay = self._overlay
        self._child = 0
        self._overlay = 0
        self._owner = 0
        self._env_started = False
        for hwnd in (child, overlay):
            if hwnd and user32.IsWindow(hwnd):
                _SURFACES.pop(hwnd, None)
                user32.DestroyWindow(hwnd)

    def _teardown(self) -> None:
        self._destroy_child()
        if self._owned_parent and user32.IsWindow(self._owned_parent):
            user32.DestroyWindow(self._owned_parent)
        self._owned_parent = 0
