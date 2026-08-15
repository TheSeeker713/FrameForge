"""v0.5.3 — progress bar, failed cue without selection, download/retry feedback."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.components.job_card import build_job_card, status_colors
from frameforge.ui_flet.job_view import card_view
from frameforge.ui_flet.theme import COLORS


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "p.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_active_download_card_has_progress_bar(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.bridge.enqueue_url("https://example.com/v", title="clip")
    ui.repo.update_status(job.id, "downloading", progress=40)
    ui.repo.update_progress(job.id, 40, speed_str="1.2 MiB/s", eta_str="00:10")
    ui.build()
    card = ui.queue_list.controls[0]
    assert card.data["progress_bar"] is not None
    assert isinstance(card.data["progress_bar"], ft.ProgressBar)
    assert abs((card.data["progress_bar"].value or 0) - 0.4) < 0.02
    assert "1.2 MiB/s" in card.data["progress_label"].value
    view = card.data["view"]
    assert view["status"] == "Downloading"
    ui.tick()
    ui.repo.update_progress(job.id, 70, speed_str="2 MiB/s")
    ui.update_active_progress(ui.repo.get(job.id))
    assert abs((card.data["progress_bar"].value or 0) - 0.7) < 0.02
    ui.shutdown()


def test_failed_pill_and_cause_visible_without_selection(tmp_path: Path):
    repo = JobRepository(tmp_path / "f.db")
    job = repo.enqueue("https://example.com/bad", title="nope")
    annotate_job_error(repo, job.id, "Sign in to confirm you’re not a bot")
    loaded = repo.get(job.id)
    view = card_view(loaded, selected=False, expanded=False)
    assert view["failed"] is True
    assert view["cause"]
    card = build_job_card(
        loaded,
        selected=False,
        expanded=False,
        show_progress=False,
    )
    assert card.data["failed"] is True
    border = card.border
    color = getattr(getattr(border, "left", None), "color", None) or getattr(border, "color", None)
    assert color == COLORS["danger"]
    assert card.bgcolor == COLORS["danger_bg"]
    bg, fg = status_colors("Failed")
    assert fg == COLORS["danger"]
    blocked = repo.enqueue("https://example.com/4k")
    repo.update_status(blocked.id, "completed")
    repo.set_source_resolution(blocked.id, 3840, 2160)
    bview = card_view(repo.get(blocked.id))
    assert bview["status"] == "BLOCKED 4K+"
    assert bview["failed"] is False
    bbg, bfg = status_colors("BLOCKED 4K+")
    assert bfg == COLORS["warn"]
    repo.close()


def test_download_all_sets_immediate_activity_and_progress_on_armed_pending(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.bridge.enqueue_url("https://example.com/a")
    ui.bridge.enqueue_url("https://example.com/b")
    ui.build()
    ui.download_all_pending()
    assert ui.worker.is_armed is True
    assert ui._activity_note is not None
    assert "Starting" in ui._activity_note
    card = ui.queue_list.controls[0]
    assert card.data.get("progress_bar") is not None
    status = ui.header.data["status"].content.value
    assert "Starting" in status
    ui.shutdown()


def test_retry_selected_sets_activity_note(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.bridge.enqueue_url("https://example.com/f")
    annotate_job_error(ui.repo, job.id, "HTTP Error 403")
    ui.build()
    ui.selected_ids = {job.id}
    ui.retry_selected_failed()
    status = ui.repo.get(job.id).status
    assert status != "failed"
    assert status in {"pending", "downloading"}
    assert ui._activity_note is not None
    ui.shutdown()
