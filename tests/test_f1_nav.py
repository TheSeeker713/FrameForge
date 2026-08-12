"""F1 — cross-tab focus and invalid action rejection."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.gui.actions import can_cancel, can_download, can_upscale
from frameforge.queue.worker import SequentialWorker


def test_invalid_actions_rejected(tmp_path: Path):
    repo = JobRepository(tmp_path / "a.db")
    failed = repo.enqueue("https://example.com/fail", title="fail")
    repo.update_status(failed.id, "failed", error="nope")
    assert can_download(repo.get(failed.id)) is False
    assert can_upscale(repo.get(failed.id)) is False
    assert can_cancel(repo.get(failed.id)) is False

    pending = repo.enqueue("https://example.com/p")
    assert can_download(repo.get(pending.id)) is True
    assert can_upscale(repo.get(pending.id)) is False

    done = repo.enqueue("https://example.com/d")
    repo.update_status(done.id, "completed", progress=100)
    assert can_upscale(repo.get(done.id)) is False  # no local file
    clip = tmp_path / "x.bin"
    clip.write_bytes(b"abc")
    repo.set_paths(done.id, download_path=str(clip), output_path=str(clip))
    assert can_upscale(repo.get(done.id)) is True

    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    try:
        worker.request_upscale_ids([failed.id], start_loop=False)
        raise AssertionError("upscale of failed job should raise")
    except ValueError:
        pass
    repo.close()


def test_focus_job_syncs_queue_and_history_ids(tmp_path: Path):
    import pytest

    try:
        from frameforge.gui.app import FrameForgeApp

        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        job = repo.enqueue("https://example.com/a", title="A")
        repo.update_status(job.id, "completed", progress=100)
        app.refresh_queue()
        assert app.focus_job(job.id)
        assert app.queue_list.selected_ids == {job.id}
        assert app.history_list.selected_ids == {job.id}
        assert app._selected_ids == {job.id}
    finally:
        app.destroy()
        repo.close()
