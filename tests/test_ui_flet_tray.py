"""Minimize hides to the tray. Downloads keep running. The tray can import and control the queue."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
from tests.flet_fakes import FakePage
from tests.test_tray_service import _FakeIcon


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "tray.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui._tray_icon_factory = _FakeIcon
    ui.page = FakePage()
    return ui


def _menu_texts(ui: FrameForgeUi) -> str:
    menu = ui.tray._icon.menu
    texts = []
    for item in menu:
        text = getattr(item, "text", None)
        if callable(text):
            try:
                text = text(ui.tray._icon)
            except TypeError:
                text = text()
        if text:
            texts.append(str(text))
    return " ".join(texts).lower()


def test_settings_has_no_close_to_tray_switch(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    dlg = build_settings_dialog(repo, on_save=lambda _s: None, on_close=lambda: None)
    labels = []

    def walk(ctrl):
        label = getattr(ctrl, "label", None)
        if isinstance(label, str):
            labels.append(label)
        content = getattr(ctrl, "content", None)
        if content is not None:
            walk(content)
        for child in getattr(ctrl, "controls", None) or []:
            walk(child)

    walk(dlg)
    blob = " ".join(labels)
    assert "Close to system tray" not in blob
    assert "Pause queue on bot-check / login failures" in blob
    assert "tray" not in (dlg.data or {})


def test_minimize_hides_to_tray_and_keeps_the_worker(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.repo.enqueue("https://example.com/keep")
    ui.worker._armed.set()
    try:
        assert ui.minimize_window() == "tray"
        assert ui.page.window.visible is False
        assert ui.page.window.skip_task_bar is True
        assert ui.page.window.minimized is False
        assert ui.worker.is_armed is True
        assert ui.repo.get(job.id).status == "pending"
        assert ui.tray.is_running is True
        blob = _menu_texts(ui)
        assert "show frameforge" in blob
        assert "download all pending" in blob
        assert "import url list" in blob
        assert "import completed downloads" in blob
        assert "quit" in blob
        assert "pause" in blob

        ui.show_from_tray()
        assert ui.page.window.visible is True
        assert ui.page.window.skip_task_bar is False
        assert ui.worker.is_armed is True

        raised = {"ok": False}

        async def _to_front() -> None:
            raised["ok"] = True

        ui.page.window.to_front = _to_front
        ui.show_from_tray()
        assert raised["ok"] is True
    finally:
        ui.shutdown()


def test_native_minimize_event_hides_to_tray(tmp_path: Path):
    ui = _ui(tmp_path)
    try:
        event = type("E", (), {"type": ft.WindowEventType.MINIMIZE})()
        ui._on_window_event(event)
        assert ui.page.window.visible is False
        assert ui._in_tray is True
        ui._on_window_event(event)
        assert ui.page.window.visible is False
    finally:
        ui.shutdown()


def test_tray_pause_resume_and_import(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.repo.enqueue("https://example.com/pause")
    claimed = ui.repo.claim_next_pending()
    assert claimed.id == job.id
    seen: list[str] = []
    ui.import_file = lambda path=None: seen.append("urls")  # type: ignore[method-assign]
    ui.import_completed_downloads = lambda _e=None: seen.append("completed")  # type: ignore[method-assign]
    try:
        ui.hide_to_tray()
        assert ui._tray_pause_label() == "Pause current"
        ui._tray_pause_resume()
        assert ui.repo.get(job.id).status == "paused"
        assert ui._tray_pause_label() == "Resume current"
        ui._tray_import_urls()
        assert ui.page.window.visible is True
        assert seen == ["urls"]
        ui.hide_to_tray()
        ui._tray_import_completed()
        assert seen == ["urls", "completed"]
        assert ui.page.window.visible is True
    finally:
        ui.shutdown()
