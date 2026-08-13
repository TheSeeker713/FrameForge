"""Phase E — remaining Flet dialogs and overflow map."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.gui.exit_policy import CHOICE_PAUSE_AND_QUIT, CHOICES
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
    q = ui.open_quit_busy()
    titles = [t.title.value for t in q.content.controls]
    assert any("Cancel download" in t for t in titles)
    assert any("Pause download" in t for t in titles)
    assert any("Wait until finished" in t for t in titles)
    auth = ui.open_authenticate("https://www.youtube.com/watch?v=x")
    assert "Authenticate" in str(auth.title.value)
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
