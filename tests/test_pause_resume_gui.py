"""Step 1.4 — GUI pause/resume eligibility and handlers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.actions import can_cancel, can_download, can_pause, can_resume


def test_pause_resume_eligibility_by_status():
    pending = SimpleNamespace(status="pending")
    downloading = SimpleNamespace(status="downloading")
    upscaling = SimpleNamespace(status="upscaling")
    paused = SimpleNamespace(status="paused")
    cancelled = SimpleNamespace(status="cancelled")
    failed = SimpleNamespace(status="failed")
    completed = SimpleNamespace(status="completed")

    assert can_pause(downloading) is True
    assert can_pause(upscaling) is True
    assert can_pause(pending) is False
    assert can_pause(paused) is False
    assert can_pause(cancelled) is False

    assert can_resume(paused) is True
    assert can_resume(downloading) is False
    assert can_resume(pending) is False
    assert can_resume(cancelled) is False
    assert can_resume(failed) is False

    assert can_download(paused) is False
    assert can_cancel(paused) is True
    assert can_cancel(completed) is False


def test_gui_pause_resume_call_worker(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    job = repo.enqueue("https://example.com/p", title="p")
    repo.claim_next_pending()
    assert repo.get(job.id).status == "downloading"

    try:
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    calls: list[tuple[str, int]] = []
    real_pause = app.worker.pause_job
    real_resume = app.worker.resume_job

    def spy_pause(jid: int):
        calls.append(("pause", jid))
        return real_pause(jid)

    def spy_resume(jid: int):
        calls.append(("resume", jid))
        return real_resume(jid)

    app.worker.pause_job = spy_pause  # type: ignore[method-assign]
    app.worker.resume_job = spy_resume  # type: ignore[method-assign]
    app.worker.download_handler = lambda j, r: r.set_paths(
        j.id, download_path=str(tmp_path / "x.bin"), output_path=str(tmp_path / "x.bin")
    )
    (tmp_path / "x.bin").write_bytes(b"ok")
    try:
        app.queue_list.set_selected({job.id})
        app._selected_ids = {job.id}
        app.pause_selected()
        assert ("pause", job.id) in calls
        assert repo.get(job.id).status == "paused"
        panel = app.format_error_panel_text(repo.get(job.id))
        assert "Paused" in panel
        assert "paused" in app.progress_label.cget("text").lower()

        app.resume_selected()
        assert ("resume", job.id) in calls
        assert repo.get(job.id).status != "paused"
        app.worker.stop(timeout=5)
    finally:
        app.worker.stop(timeout=5)
        app.destroy()
        repo.close()
