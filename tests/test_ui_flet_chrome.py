"""Phase C — Flet chrome: hero, --gui entry, settings single-instance."""

from __future__ import annotations

import inspect
from pathlib import Path

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi, build_header, build_hero, create_ui
from frameforge.__main__ import main as cli_main


def test_header_has_settings_and_authenticate_icons():
    header = build_header()
    tips = [c.tooltip for c in header.controls if isinstance(c, ft.IconButton)]
    assert tips == ["Settings", "Authenticate"]


def test_hero_add_and_import_labels():
    hero = build_hero()
    add = hero.data["add"]
    imp = hero.data["import"]
    assert "+ Add to Queue" in str(add.content)
    assert "Import TXT/MD" in str(imp.content)


def test_gui_cli_launches_flet_not_customtkinter():
    src = inspect.getsource(cli_main)
    assert "frameforge.ui_flet.app" in src
    assert "run_gui" in src
    assert "gui.app import create_app" not in src


def test_create_ui_does_not_arm(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    repo.enqueue("https://example.com/p")
    crashed = repo.enqueue("https://example.com/c")
    repo.update_status(crashed.id, "downloading")
    ui = create_ui(
        repo=repo,
        start_worker=False,
        worker=SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05),
    )
    assert ui.worker.is_armed is False
    assert repo.get(crashed.id).status == "pending"
    assert repo.count_by_status("pending") == 2
    ui.shutdown()


def test_settings_single_instance(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    first = ui.open_settings()
    assert ui.bridge.settings_open is True
    second = ui.open_settings()
    assert first is second
    assert ui.settings_focus_count == 1
    titles = []

    def walk(ctrl):
        if isinstance(ctrl, ft.Text) and ctrl.value:
            titles.append(ctrl.value)
        content = getattr(ctrl, "content", None)
        if content is not None:
            walk(content)
        for child in getattr(ctrl, "controls", None) or []:
            walk(child)
        for child in getattr(ctrl, "actions", None) or []:
            walk(child)

    walk(first)
    blob = " ".join(titles)
    assert "Download and Quality" in blob
    assert "AI and Upscaling" in blob
    assert "System Behavior" in blob
    ui.shutdown()


def test_add_url_enqueues_without_arming(tmp_path: Path):
    repo = JobRepository(tmp_path / "a.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.build()
    ui.hero.data["url"].value = "https://example.com/video"
    ui.listing_probe = lambda _url: (None, "example.com", None)
    job = ui.add_url()
    assert job is not None
    assert job.status == "pending"
    assert job.extractor == "example.com"
    assert worker.is_armed is False
    ui.shutdown()
