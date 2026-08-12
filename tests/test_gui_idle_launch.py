"""Step B1 — GUI launch and enqueue must not arm downloads."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.pipeline import build_worker
from frameforge.queue.worker import SequentialWorker
from tests.test_tray_service import _FakeIcon


def test_prepare_idle_launch_does_not_start_or_arm(tmp_path: Path):
    repo = JobRepository(tmp_path / "idle.db")
    job = repo.enqueue("https://example.com/a")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    recovered = worker.prepare_idle_launch()
    assert recovered == []
    assert worker.is_armed is False
    assert worker.is_running is False
    time.sleep(0.15)
    assert repo.get(job.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()


def test_gui_enqueue_stays_pending_worker_idle(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    try:
        app = FrameForgeApp(
            repo=repo,
            start_worker=False,
            recover_on_launch=True,
            tray_icon_factory=_FakeIcon,
        )
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert app.worker.is_armed is False
        assert app.worker.is_running is False
        job = repo.enqueue("https://example.com/queued")
        time.sleep(0.2)
        assert repo.get(job.id).status == "pending"
        assert app.worker.is_armed is False
        assert app.worker.is_running is False
        app._enqueue_single_url = lambda url: repo.enqueue(url)  # avoid network probe
        # playlist/bulk paths must not arm either
        from frameforge.download.playlist import PlaylistEntry, PlaylistListing

        listing = PlaylistListing(
            url="https://example.com/pl",
            title="p",
            playlist_id="PL1",
            entries=[PlaylistEntry(1, "https://example.com/p1", title="p1")],
        )
        app.enqueue_playlist_selection(listing, {1})
        assert app.worker.is_armed is False
        assert all(j.status == "pending" for j in repo.list_jobs())
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
