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
    assert "2160" in (bview.get("blocked_4k_hint") or "")
    bcard = build_job_card(repo.get(blocked.id), selected=False, expanded=False, show_progress=False)
    row = bcard.content.controls[0]
    tips = [str(getattr(c, "tooltip", "") or "") for c in row.controls]
    assert any("Upscale blocked" in t for t in tips)
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


def test_tick_updates_active_progress_without_rebuild(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.bridge.enqueue_url("https://example.com/v", title="clip")
    ui.repo.update_status(job.id, "downloading", progress=10)
    ui.repo.update_progress(job.id, 10, speed_str="1 MiB/s", eta_str="1:00")
    ui.build()
    first_card = ui.queue_list.controls[0]
    ui.repo.update_progress(job.id, 55, speed_str="2 MiB/s", eta_str="0:20")
    ui.tick()
    assert ui.queue_list.controls[0] is first_card
    assert abs((first_card.data["progress_bar"].value or 0) - 0.55) < 0.02
    assert "2 MiB/s" in first_card.data["progress_label"].value
    ui.shutdown()


def test_click_thumbnail_plays_or_toasts(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.reveal_launch = False
    media = tmp_path / "ok.mp4"
    media.write_bytes(b"not-a-real-video")
    done = ui.bridge.enqueue_url("https://example.com/d", title="d")
    ui.repo.update_status(done.id, "completed")
    ui.repo.set_paths(done.id, download_path=str(media), output_path=str(media))
    ui.build()
    card = ui.queue_list.controls[0]
    thumb = card.content.controls[0].controls[1]
    assert thumb.data.get("playable") is True
    assert "play" in str(thumb.tooltip or "").lower()
    ui.play_job(done.id)
    missing = ui.bridge.enqueue_url("https://example.com/gone", title="gone")
    ui.repo.update_status(missing.id, "completed")
    ui.repo.set_paths(missing.id, download_path=str(tmp_path / "nope.mp4"), output_path=str(tmp_path / "nope.mp4"))
    ui.play_job(missing.id)
    assert ui.last_toast and "not found" in ui.last_toast.lower()
    ui.shutdown()


def test_idle_status_explains_stop_and_fail_pause(tmp_path: Path):
    from frameforge.ui_flet.components.status_pill import status_pill_text

    assert "stopped" in status_pill_text(active_status=None, pending_count=3, idle_reason="stopped").lower()
    assert "paused after failure" in status_pill_text(
        active_status=None, pending_count=2, idle_reason="fail_pause"
    ).lower()
    ui = _ui(tmp_path)
    ui.bridge.enqueue_url("https://example.com/p")
    ui.build()
    ui.stop_active()
    assert ui._idle_reason == "stopped"
    assert "stopped" in (ui._activity_note or "").lower()
    ui.shutdown()

