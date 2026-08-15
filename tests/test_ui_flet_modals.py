"""Phase E — remaining Flet dialogs and overflow map."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.job_view import overflow_actions


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "m.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_modals_have_locked_actions(tmp_path: Path):
    ui = _ui(tmp_path)
    fmt = ui.open_format_modal([])
    assert "Set format" in str(fmt.title.value)
    bulk = ui.open_bulk_confirm(18, 3)
    blob = str(bulk.content.controls[2].value)
    assert "will not start" in blob.lower() or "press Download" in blob
    pl = ui.open_playlist_modal("Summer Reel", list(range(8)))
    assert "Playlist" in str(pl.title.value)
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    q = ui.open_quit_busy()
    body = str(getattr(q.content, "value", q.content))
    assert "in progress" in body.lower() or "Quit FrameForge" in str(q.title.value)
    action_blob = " ".join(str(getattr(a, "content", a)) for a in q.actions)
    assert "Quit" in action_blob
    assert "Cancel" in action_blob
    assert "Force quit now" not in action_blob
    auth = ui.open_authenticate("https://www.youtube.com/watch?v=x")
    assert "Authenticate" in str(auth.title.value)
    from frameforge.paths import cookies_dir

    assert "cookies" in str(auth.data["cookies_dir"]).lower()
    assert Path(auth.data["cookies_dir"]).name == "cookies"
    assert cookies_dir().name == "cookies"
    ui.shutdown()


def test_overflow_includes_remove_and_format():
    class J:
        id = 1
        status = "failed"
        download_path = None
        output_path = None
        upscale_blocked = False

        def options(self):
            return {}

    acts = overflow_actions(J())
    assert "retry" in acts
    assert "remove_from_queue" in acts
    assert "set_format" in acts


def test_queue_history_use_scrollable_lists(tmp_path: Path):
    import flet as ft

    ui = _ui(tmp_path)
    ui.build()
    assert isinstance(ui.queue_list, ft.ListView)
    assert isinstance(ui.history_list, ft.ListView)
    assert isinstance(ui.thumbs_grid, ft.GridView)
    ui.shutdown()
