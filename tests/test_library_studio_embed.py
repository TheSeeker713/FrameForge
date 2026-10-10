"""The Library tab hosts the WebGL studio and passes real library rows."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from urllib.request import Request, urlopen

from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.library_studio import LOCKED_LOOK
from frameforge.ui_flet.library_surface import find_frameforge_hwnd, frameforge_title
from tests.flet_fakes import FakePage
from tests.test_library import _clip, _repo


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    return ui


def _origin(ui: FrameForgeUi) -> str:
    url = str(ui.library_studio_host.data["url"])
    head, _query = url.split("?", 1)
    return head.rsplit("/", 1)[0]


def _get(url: str) -> bytes:
    with urlopen(url, timeout=5) as response:
        return response.read()


def _foreign_flet_child_count() -> int | None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    found: list[int] = []

    def visit(hwnd: int, _lp: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value != frameforge_title():
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, int(pid.value))
        if not handle:
            return True
        try:
            size = wintypes.DWORD(1024)
            exe = ctypes.create_unicode_buffer(1024)
            kernel32.QueryFullProcessImageNameW(handle, 0, exe, ctypes.byref(size))
        finally:
            kernel32.CloseHandle(handle)
        if exe.value.lower().endswith("flet.exe") and int(pid.value) != __import__("os").getpid():
            found.append(int(hwnd))
        return True

    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit)
    user32.EnumWindows(callback, 0)
    if len(found) != 1:
        return None
    children: list[int] = []

    def child(hwnd: int, _lp: int) -> bool:
        children.append(int(hwnd))
        return True

    child_cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(child)
    user32.EnumChildWindows(found[0], child_cb, 0)
    return len(children)


def test_library_tab_hosts_studio_and_binds_rows(tmp_path: Path):
    from PIL import Image

    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    titles = ("Interview clip", "Recital", "Lecture excerpt", "Demo recording")
    paths: list[Path] = []
    thumb = tmp_path / "still.jpg"
    Image.new("RGB", (16, 9), (20, 40, 80)).save(thumb, "JPEG")
    for index, title in enumerate(titles):
        src = _clip(tmp_path / "dl" / f"{index}.mp4")
        paths.append(src)
        ui.library.add_item(
            path=src,
            title=title,
            source="local",
            width=1280,
            height=720,
            thumb_path=str(thumb) if index == 0 else None,
        )
    ui.library_sort = "title"
    ui.refresh_library()
    host = ui.library_studio_host
    assert ui.library_browser in ui.library_stack.controls
    assert host not in ui.library_stack.controls
    assert ui.library_grid not in ui.library_stack.controls
    assert host.visible is False
    assert ui.library_empty.visible is False
    assert ui.library_browser.data["kind"] == "library_books"
    assert "Movies" in ui.library_browser.data["books"]
    assert host.data["kind"] == "library_studio"
    assert host.data["embed"] is True
    assert host.data["look"] == LOCKED_LOOK
    rows = host.data["rows"]
    assert [row["title"] for row in rows] == sorted(titles, key=str.lower)
    by_title = {row["title"]: row for row in rows}
    assert Path(by_title["Interview clip"]["path"]).resolve() == paths[0].resolve()
    assert by_title["Interview clip"]["thumb"]
    for src, title in zip(paths, titles, strict=True):
        assert Path(by_title[title]["path"]).resolve() == src.resolve()
        assert src.is_file()
    assert isinstance(ui.queue_list, __import__("flet").ListView)
    assert isinstance(ui.history_list, __import__("flet").ListView)

    origin = _origin(ui)
    document = json.loads(_get(origin + "/api/shelf"))
    assert document["look"] == LOCKED_LOOK
    assert [clip["title"] for clip in document["clips"]] == [row["title"] for row in rows]
    assert [Path(clip["path"]).resolve() for clip in document["clips"]] == [
        Path(row["path"]).resolve() for row in rows
    ]
    thumb_bytes = _get(origin + by_title["Interview clip"]["thumb"])
    assert thumb_bytes == thumb.read_bytes()
    page = _get(host.data["url"]).decode("utf-8")
    assert "studio.js" in page
    assert 'get("embed")' in page
    studio = _get(origin + "/studio.js").decode("utf-8")
    assert 'pointer: "magnetic"' in studio
    assert "grain: false" in studio
    assert "/api/shelf" in studio
    ui.shutdown()


def test_empty_library_hides_the_shelf(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    ui.refresh_library()
    assert ui.library_visible_count == 0
    assert ui.library_studio_host.visible is False
    assert ui.library_browser in ui.library_stack.controls
    assert ui.library_browser.data["books"][0] == "Movies"
    assert "Comedy" in ui.library_browser.data["folders"]
    assert ui.library_browser.data["clips"] == []
    assert ui.library_empty.visible is False
    assert ui.library_studio_host.data["rows"] == []
    assert ui.library_studio_host.data["look"] == LOCKED_LOOK
    document = json.loads(_get(_origin(ui) + "/api/shelf"))
    assert document["clips"] == []
    assert document["look"]["grain"] is False
    ui.shutdown()


def test_shelf_actions_keep_the_file_until_delete_is_confirmed(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    root = ui.library.complete_onboarding(tmp_path / "Lib")
    src = _clip(root / "stay.mp4", data=b"m" * 300)
    item = ui.library.add_item(path=src, title="Stay", source="local")
    album = ui.library.create_album("Evening")
    ui.library.place_in_album(item.id, album.id)
    assert Path(ui.library.get(item.id).path).resolve() == src.resolve()
    ui.refresh_library()
    row = ui.library_studio_host.data["rows"][0]
    assert Path(row["path"]).resolve() == src.resolve()
    assert src.is_file()

    origin = _origin(ui)
    for action in ("unlink", "delete", "open"):
        body = json.dumps({"action": action, "id": item.id}).encode("utf-8")
        request = Request(origin + "/api/shelf/action", data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
    assert ui.drain_library_studio_actions() == 3
    assert src.is_file()
    assert ui.library_player_host.visible is True
    assert ui.library_player_host.data["kind"] == "library_player"
    assert ui.last_library_player == str(src.resolve())
    ui.shutdown()


def test_unlink_dialog_does_not_delete_and_delete_is_separate(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "keep.mp4")
    item = ui.library.add_item(path=src, title="Keep")
    ui.refresh_library()
    origin = _origin(ui)
    body = json.dumps({"action": "unlink", "id": item.id}).encode("utf-8")
    request = Request(origin + "/api/shelf/action", data=body, method="POST")
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
    ui.drain_library_studio_actions()
    assert src.is_file()
    assert ui.dialogs.current.data["delete_files"] is False
    ui.close_dialog()
    body = json.dumps({"action": "delete", "id": item.id}).encode("utf-8")
    request = Request(origin + "/api/shelf/action", data=body, method="POST")
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
    ui.drain_library_studio_actions()
    assert src.is_file()
    assert ui.dialogs.current.data["delete_files"] is True
    ui.shutdown()


def test_surface_does_not_guess_the_foreground_window():
    source = Path("src/frameforge/ui_flet/library_surface.py").read_text(encoding="utf-8")
    assert "GetForegroundWindow(" not in source
    assert "DwmSetWindowAttribute(" not in source
    assert find_frameforge_hwnd() is None


def test_webview_loads_embed_without_attaching_to_another_frameforge(tmp_path: Path):
    from frameforge.ui_flet.library_surface import LibrarySurface

    before = _foreign_flet_child_count()
    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "one.mp4")
    ui.library.add_item(path=src, title="Demo recording", source="local")
    ui.refresh_library()
    surface = LibrarySurface()
    try:
        assert surface.probe_offscreen(ui.library_studio_host.data["url"], timeout=25)
        assert surface.last_error == ""
    finally:
        surface.close()
        ui.shutdown()
    after = _foreign_flet_child_count()
    if before is not None:
        assert after == before


_PARENT_PROBE = r"""
import ctypes, time
from ctypes import wintypes
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
def _proc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
proc = WNDPROC(_proc)
class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
wc = WNDCLASSW()
wc.lpfnWndProc = proc
wc.hInstance = kernel32.GetModuleHandleW(None)
wc.lpszClassName = "FrameForgeShelfParentProbe"
user32.RegisterClassW(ctypes.byref(wc))
hwnd = user32.CreateWindowExW(0x80, "FrameForgeShelfParentProbe", "FrameForgeShelfParentProbe", 0x80000000, -4000, -4000, 800, 500, None, None, wc.hInstance, None)
user32.ShowWindow(hwnd, 5)
print(int(hwnd), flush=True)
class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]
message = MSG()
while True:
    while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    time.sleep(0.02)
"""


def test_shelf_embeds_in_another_process_window():
    from frameforge.ui_flet.library_surface import LibrarySurface

    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _PARENT_PROBE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    surface = LibrarySurface()
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line.isdigit(), proc.stderr.read() if proc.stderr else line
        parent = int(line)
        assert surface.embed_into(parent, "about:blank", timeout=25)
        assert surface.last_error == ""
        user32 = ctypes.WinDLL("user32")
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        assert int(user32.GetParent(surface._child)) == parent
    finally:
        surface.close()
        proc.kill()
        proc.wait(timeout=5)
