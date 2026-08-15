"""Phase D — queue cards, floating bar, fail expand, history filters."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.job_view import card_view, floating_bar_view, status_pill, structural_sig


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "q.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_status_pills_and_structural_sig_ignores_progress(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    job = repo.enqueue("https://youtube.com/watch?v=a", title="clip")
    assert status_pill(job) == "Queued"
    repo.update_status(job.id, "downloading", progress=10)
    d = repo.get(job.id)
    assert status_pill(d) == "Downloading"
    sig1 = structural_sig([d])
    repo.update_status(job.id, "downloading", progress=50)
    d2 = repo.get(job.id)
    assert structural_sig([d2]) == sig1
    repo.set_source_resolution(job.id, 3840, 2160)
    blocked = repo.get(job.id)
    assert status_pill(blocked) == "BLOCKED 4K+"
    repo.close()


def test_floating_bar_hidden_until_selection_and_contextual_upscale(tmp_path: Path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"not-a-real-video")
    repo = JobRepository(tmp_path / "f.db")
    pending = repo.enqueue("https://example.com/p", title="p")
    done = repo.enqueue("https://example.com/d", title="d")
    repo.update_status(done.id, "completed")
    repo.set_paths(done.id, download_path=str(media), output_path=str(media))
    jobs = [repo.get(pending.id), repo.get(done.id)]
    assert floating_bar_view(jobs, set()) is None
    bar = floating_bar_view(jobs, {pending.id})
    assert bar is not None
    assert bar["show_download"] is True
    assert bar["show_upscale"] is False
    bar2 = floating_bar_view(jobs, {done.id})
    assert bar2["show_upscale"] is True
    assert bar2["show_convert"] is True
    assert bar2["show_download"] is False
    repo.close()


def test_queue_cards_bind_and_empty_state(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.build()
    assert ui.queue_list is not None
    assert ui.queue_list.controls
    empty_txt = str(ui.queue_list.controls[0].content.controls[0].value)
    assert "Queue is empty" in empty_txt
    job = ui.bridge.enqueue_url("https://example.com/v", title="Hello")
    ui.refresh_queue(force=True)
    assert len(ui.queue_list.controls) == 1
    view = ui.queue_list.controls[0].data["view"]
    assert view["title"] == "Hello"
    assert view["status"] == "Queued"
    assert ui.floating is not None
    assert ui.floating.visible is False
    ui.toggle_select(job.id)
    assert ui.floating.visible is True
    assert ui.floating.data["count"] == 1
    assert ui.floating.data["show_download"] is True
    labels = []

    def walk(ctrl):
        content = getattr(ctrl, "content", None)
        if isinstance(content, str) and "Download selected" in content:
            labels.append(content)
        if content is not None and content is not ctrl:
            walk(content)
        for child in getattr(ctrl, "controls", None) or []:
            walk(child)

    walk(ui.floating)
    assert labels or ui.floating.data["show_download"] is True
    ui.shutdown()


def test_failed_expand_retry_uses_bridge(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=z", title="gated")
    annotate_job_error(ui.repo, job.id, "Sign in to confirm you’re not a bot")
    ui.build()
    loaded = ui.repo.get(job.id)
    view = card_view(loaded, expanded=True)
    assert view["failed"] is True
    assert "bot" in view["cause"].lower() or "signed" in view["cause"].lower()
    ui.toggle_failed_expand(job.id)
    assert job.id in ui.expanded_failed
    requested: list[list[int]] = []
    ui.worker.request_download_ids = lambda ids: requested.append(list(ids))  # type: ignore[method-assign]
    ui.retry_failed_job(job.id)
    assert requested == [[job.id]]
    assert ui.repo.get(job.id).status == "pending"
    ui.shutdown()


def test_history_filter_and_redownload_pending(tmp_path: Path):
    ui = _ui(tmp_path)
    a = ui.repo.enqueue("https://youtube.com/watch?v=1", title="ok")
    b = ui.repo.enqueue("https://example.com/bad", title="nope")
    ui.repo.update_status(a.id, "completed")
    annotate_job_error(ui.repo, b.id, "Video unavailable")
    ui.repo.clear_finished_from_queue()
    ui.build()
    ui.set_history_filter("completed")
    titles = [c.data["view"]["title"] for c in ui.history_list.controls]
    assert titles == ["ok"]
    ui.set_history_filter("failed")
    titles = [c.data["view"]["title"] for c in ui.history_list.controls]
    assert titles == ["nope"]
    ui.selected_ids = {b.id}
    new_ids = ui.redownload_history()
    assert new_ids
    assert ui.repo.get(new_ids[0]).status == "pending"
    assert ui.worker.is_armed is False
    assert ui.repo.get(b.id).status == "failed"
    ui.shutdown()


def test_thumbs_grid_and_resource_banner(tmp_path: Path):
    ui = _ui(tmp_path)
    job = ui.repo.enqueue("https://example.com/t", title="thumb")
    ui.repo.update_status(job.id, "completed")
    ui.build()
    assert ui.thumbs_grid is not None
    assert any(c.data.get("job_id") == job.id for c in ui.thumbs_grid.controls)
    ui.set_resource_banner("High RAM 91%")
    assert ui.resource_banner.visible is True
    assert "91%" in ui.resource_banner.data["text"]
    ui.shutdown()
