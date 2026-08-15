"""Phase D — fail-pause five actions stay wired; no empty handlers."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.fail_pause import MODAL_ACTIONS
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage


def test_fail_pause_dialog_five_actions_and_resume_control(tmp_path: Path):
    repo = JobRepository(tmp_path / "d.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    job = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=d")
    annotate_job_error(ui.repo, job.id, "Sign in to confirm you’re not a bot")
    payload = {
        "job_id": job.id,
        "title": "gated",
        "url": job.url,
        "cause": "The site thinks this is automated traffic (bot check).",
    }
    dlg = ui._fail_pause_dialog(payload)
    labels = []
    for act in dlg.actions:
        content = getattr(act, "content", None)
        labels.append(str(content) if content is not None else "")
    blob = " ".join(labels)
    assert "Import from browser" in blob
    assert "Authenticate site" in blob
    assert "Retry this job" in blob
    assert "Skip & resume queue" in blob
    assert "Stop queue" in blob
    assert dlg.data["resume"] is not None
    assert dlg.data["status"] is not None
    assert dlg.data["browser"] is not None
    assert (dlg.data["browser"].value or "") == "chrome"
    ids = [aid for aid, _ in MODAL_ACTIONS]
    assert ids == ["import_browser", "authenticate", "retry", "skip_resume", "stop"]
    ui.shutdown()


def test_queue_chrome_floating_and_settings_clicks_are_wired(tmp_path: Path):
    from frameforge.ui_flet.components.job_card import build_floating_bar, build_queue_chrome
    from frameforge.ui_flet.components.settings_dialog import build_settings_dialog

    chrome = build_queue_chrome(
        {
            "visible": True,
            "show_download_all": True,
            "show_retry_failed": True,
            "show_clear_finished": True,
            "clear_selected_enabled": True,
        },
        on_download_all=lambda: None,
        on_retry_failed=lambda: None,
        on_clear_finished=lambda: None,
        on_clear_selected=lambda: None,
    )
    for btn in chrome.content.controls:
        assert btn.on_click is not None

    bar = build_floating_bar(
        {
            "count": 1,
            "show_download": True,
            "show_upscale": False,
            "show_convert": False,
            "show_retry": True,
            "show_clear": True,
        },
        on_download=lambda: None,
        on_retry=lambda: None,
        on_clear=lambda: None,
        on_more=lambda _a: None,
    )
    for ctrl in bar.content.controls:
        if isinstance(ctrl, (ft.FilledButton, ft.OutlinedButton)):
            assert ctrl.on_click is not None
        if isinstance(ctrl, ft.PopupMenuButton):
            assert all(it.on_click is not None for it in ctrl.items)

    dlg = build_settings_dialog(JobRepository(tmp_path / "s.db"), on_save=lambda _s: None, on_close=lambda: None)
    assert all(a.on_click is not None for a in dlg.actions)
