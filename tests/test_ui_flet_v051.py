"""v0.5.1 P0 interaction: dialogs, import, More menu, queue chrome, shutdown."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import flet as ft

from frameforge.download.cookie_validate import clear_session_cookie_validation
from frameforge.download.cookies import cookie_path_for_url
from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi, apply_page_chrome, run_gui
from frameforge.ui_flet.components.job_card import build_floating_bar
from frameforge.ui_flet.job_view import more_menu_items
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from frameforge.ui_flet.theme import COLORS
from tests.flet_fakes import FakePage


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "v051.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def _netscape(path: Path) -> Path:
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\ttest\n",
        encoding="utf-8",
    )
    return path


def test_authenticate_closes_via_x_cancel_and_dismiss(tmp_path: Path):
    ui = _ui(tmp_path)
    page = FakePage()
    ui.page = page
    dlg = ui.open_authenticate("https://www.youtube.com/watch?v=x")
    assert ui.auth_open is True
    assert ui.dialogs.kind == "auth"
    assert page.dialog is dlg
    close_btn = dlg.actions[0]
    assert isinstance(close_btn, ft.IconButton)
    assert close_btn.tooltip == "Close"
    close_btn.on_click()
    assert ui.auth_open is False
    assert ui.dialogs.current is None
    assert page.popped >= 1

    dlg2 = ui.open_authenticate()
    cancel = next(
        a
        for a in dlg2.actions
        if isinstance(a, ft.OutlinedButton) and str(getattr(a, "content", "")) == "Cancel"
    )
    cancel.on_click()
    assert ui.auth_open is False

    dlg3 = ui.open_authenticate()
    dlg3.on_dismiss()
    assert ui.auth_open is False
    ui.shutdown()


def test_authenticate_second_open_does_not_stack(tmp_path: Path):
    ui = _ui(tmp_path)
    page = FakePage()
    ui.page = page
    first = ui.open_authenticate("https://example.com/")
    second = ui.open_authenticate("https://example.com/other")
    assert first is second
    assert page.dialogs == [first]
    ui.shutdown()


def _write_site_cookies(url: str) -> Path:
    path = cookie_path_for_url(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\ttest\n",
        encoding="utf-8",
    )
    return path


def test_authenticate_firefox_success_stays_open_error_stays(tmp_path: Path):
    clear_session_cookie_validation()
    ui = _ui(tmp_path)
    page = FakePage()
    ui.page = page
    ui.cookie_probe = lambda url, cookiefile: {"id": "z", "title": "ok"}

    def ok_import(url, browser="firefox"):
        _write_site_cookies(url)
        return SimpleNamespace(ok=True, message="ok")

    ui.import_browser_fn = ok_import
    dlg = ui.open_authenticate("https://www.youtube.com/watch?v=z")
    assert dlg.data.get("on_chrome") is not None
    assert dlg.data.get("on_edge") is not None
    ui._auth_chrome()
    assert ui.auth_open is True
    assert ui.dialogs.current is dlg
    assert dlg.data["error"].visible is True
    assert "valid" in dlg.data["error"].value.lower() or "close" in dlg.data["error"].value.lower()

    ui.import_browser_fn = lambda url, browser="firefox": SimpleNamespace(ok=False, message="locked")
    dlg = ui.open_authenticate("https://www.youtube.com/watch?v=z")
    ui._auth_firefox()
    assert ui.auth_open is True
    assert dlg.data["error"].visible is True
    assert "locked" in dlg.data["error"].value
    ui.shutdown()


def test_authenticate_cookies_txt_success_stays_open(tmp_path: Path):
    clear_session_cookie_validation()
    ui = _ui(tmp_path)
    page = FakePage()
    ui.page = page
    ui.cookie_probe = lambda url, cookiefile: {"id": "z", "title": "ok"}
    ui.open_authenticate("https://www.youtube.com/watch?v=z")
    cookie = _netscape(tmp_path / "cookies.txt")
    ui.import_cookies_txt_path(cookie)
    assert ui.auth_open is True
    ui.shutdown()


def test_settings_and_other_modals_close(tmp_path: Path):
    ui = _ui(tmp_path)
    page = FakePage()
    ui.page = page
    s = ui.open_settings()
    s.data["cancel"]()
    assert ui.bridge.settings_open is False
    assert ui.dialogs.current is None

    fmt = ui.open_format_modal([])
    fmt.data["cancel"]()
    assert ui.format_open is False

    bulk = ui.open_bulk_confirm(1, 0)
    bulk.data["on_cancel"]()
    assert ui.bulk_open is False

    pl = ui.open_playlist_modal("Reel", [0, 1])
    pl.data["on_cancel"]()
    assert ui.playlist_open is False
    ui.shutdown()


def test_window_close_idle_opens_quit_confirm(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    assert ui.exit_process_on_quit is False
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    assert ui._shutdown_complete is False
    ui.shutdown()


def test_window_close_busy_opens_quit_modal(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    assert ui._shutdown_complete is False
    ui.shutdown()


def test_import_txt_enqueues_pending_without_arming(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.build()
    listing = tmp_path / "urls.txt"
    listing.write_text("https://example.com/one\nhttps://example.com/two\n", encoding="utf-8")
    dlg = ui.import_file(str(listing))
    assert dlg is not None
    assert ui.dialogs.kind == "bulk"
    assert ui.worker.is_armed is False
    ui.confirm_bulk_import()
    assert ui.repo.count_by_status("pending") == 2
    assert ui.worker.is_armed is False
    ui.shutdown()


def test_more_menu_items_invoke_real_handlers(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.reveal_launch = False
    ui.build()
    pending = ui.bridge.enqueue_url("https://example.com/p", title="p")
    failed = ui.bridge.enqueue_url("https://example.com/f", title="f")
    annotate_job_error(ui.repo, failed.id, "HTTP Error 403")
    media = tmp_path / "done.mp4"
    media.write_bytes(b"x")
    done = ui.bridge.enqueue_url("https://example.com/d", title="d")
    ui.repo.update_status(done.id, "completed")
    ui.repo.set_paths(done.id, download_path=str(media), output_path=str(media))
    ui.selected_ids = {pending.id, failed.id, done.id}
    ui.worker.request_upscale_ids = lambda ids, **k: list(ids)  # type: ignore[method-assign]
    ui.worker.request_convert_ids = lambda ids: None  # type: ignore[method-assign]
    ui.worker.request_download_ids = lambda ids: None  # type: ignore[method-assign]
    ui.worker.request_download_all = lambda: None  # type: ignore[method-assign]
    items = more_menu_items(ui.queue_jobs(), ui.selected_ids)
    for required in (
        "download_selected",
        "upscale",
        "convert",
        "set_format",
        "clear_selected",
        "retry_selected",
        "select_recommended",
        "clear_finished",
    ):
        assert required in items
    for aid in items:
        ui._on_more(aid)
        assert ui.last_more_action == aid
    assert "unwired" not in "".join(ui.more_invocations)
    ui.shutdown()


def test_more_control_is_not_nested_button():
    spec = {
        "count": 1,
        "show_download": True,
        "show_upscale": False,
        "show_convert": False,
        "show_clear": True,
        "show_retry": False,
        "more_items": ["clear_selected", "clear_finished"],
    }
    called: list[str] = []
    bar = build_floating_bar(spec, on_more=lambda a: called.append(a))
    more = bar.content.controls[-1]
    assert isinstance(more, ft.PopupMenuButton)
    assert not isinstance(more.content, ft.OutlinedButton)
    item = more.items[0]
    item.on_click()
    assert called == ["clear_selected"]


def test_queue_chrome_visibility_and_handlers(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.build()
    spec = queue_chrome_spec(ui.queue_jobs(), set())
    assert spec["visible"] is False

    pending = ui.bridge.enqueue_url("https://example.com/p")
    ui.refresh_queue(force=True)
    chrome = ui.queue_chrome.data
    assert chrome["show_download_all"] is True
    assert chrome["show_retry_failed"] is False
    assert chrome["clear_selected_enabled"] is False

    failed = ui.bridge.enqueue_url("https://example.com/f")
    annotate_job_error(ui.repo, failed.id, "HTTP Error 403")
    done = ui.bridge.enqueue_url("https://example.com/d")
    ui.repo.update_status(done.id, "completed")
    blocked = ui.bridge.enqueue_url("https://example.com/4k")
    ui.repo.update_status(blocked.id, "completed")
    ui.repo.set_source_resolution(blocked.id, 3840, 2160)
    ui.refresh_queue(force=True)
    chrome = ui.queue_chrome.data
    assert chrome["show_retry_failed"] is True
    assert chrome["show_clear_finished"] is True
    assert chrome["failed_count"] == 1
    assert ui.queue_chrome.visible is True

    ui.toggle_select(failed.id)
    assert ui.queue_chrome.data["clear_selected_enabled"] is True
    armed: list[list[int]] = []
    ui.worker.request_download_ids = lambda ids: armed.append(list(ids))  # type: ignore[method-assign]
    ui.retry_selected_failed()
    assert ui.repo.get(failed.id).status == "pending"
    assert armed == []
    assert "Download" in (ui._activity_note or "")
    ui.selected_ids = {done.id}
    ui.clear_selected()
    assert ui.repo.get(done.id).options().get("queue_hidden") or done.id not in {
        j.id for j in ui.repo.list_jobs()
    }

    requested: list[list[int]] = []
    ui.worker.request_download_ids = lambda ids: requested.append(list(ids))  # type: ignore[method-assign]
    annotate_job_error(ui.repo, pending.id, "fail")
    ui.retry_all_failed()
    assert requested == []
    assert ui.repo.get(pending.id).status == "pending"
    ui.shutdown()


def test_window_chrome_opaque_no_shadow_ghost():
    page = FakePage()
    apply_page_chrome(page)
    assert page.window.bgcolor == COLORS["app_bg"]
    assert page.window.opacity == 1.0
    assert page.window.shadow is False
    assert page.window.title_bar_hidden is False
    assert page.window.frameless is False


def test_run_gui_refuses_second_instance(tmp_path: Path, monkeypatch):
    import frameforge.ui_flet.app as appmod

    monkeypatch.setattr(appmod, "_GUI_RUNNING", True)
    try:
        raised = False
        try:
            run_gui()
        except RuntimeError as exc:
            raised = "already running" in str(exc)
        assert raised is True
    finally:
        monkeypatch.setattr(appmod, "_GUI_RUNNING", False)
