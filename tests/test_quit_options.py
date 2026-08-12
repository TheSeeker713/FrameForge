"""Step 2.2 — three quit options and GUI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.exit_policy import (
    CHOICE_CANCEL_AND_QUIT,
    CHOICE_PAUSE_AND_QUIT,
    CHOICE_WAIT_THEN_QUIT,
    OUTCOME_EXIT,
    OUTCOME_WAIT,
    QUIT_OPTION_CANCEL,
    QUIT_OPTION_PAUSE,
    QUIT_OPTION_WAIT,
    apply_quit_choice,
)
from frameforge.queue.worker import SequentialWorker


def _active_worker(tmp_path: Path, name: str):
    db = tmp_path / f"{name}.db"
    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/active")
    repo.claim_next_pending()
    other = repo.enqueue("https://example.com/queued")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    worker._armed.set()
    return db, repo, worker, job, other


def test_quit_cancel_marks_cancelled(tmp_path: Path):
    _db, repo, worker, job, other = _active_worker(tmp_path, "c")
    assert apply_quit_choice(worker, CHOICE_CANCEL_AND_QUIT) == OUTCOME_EXIT
    assert repo.get(job.id).status == "cancelled"
    assert repo.get(other.id).status == "pending"
    assert worker.wait_to_quit is False
    repo.close()


def test_quit_pause_survives_reopen(tmp_path: Path):
    db, repo, worker, job, other = _active_worker(tmp_path, "p")
    assert apply_quit_choice(worker, CHOICE_PAUSE_AND_QUIT) == OUTCOME_EXIT
    assert repo.get(job.id).status == "paused"
    assert repo.get(other.id).status == "pending"
    job_id = job.id
    repo.close()

    repo2 = JobRepository(db)
    loaded = repo2.get(job_id)
    assert loaded.status == "paused"
    assert repo2.claim_next_pending() is not None  # other pending is claimable
    assert repo2.get(job_id).status == "paused"
    repo2.close()


def test_quit_wait_disarms_claims(tmp_path: Path):
    _db, repo, worker, job, other = _active_worker(tmp_path, "w")
    assert apply_quit_choice(worker, CHOICE_WAIT_THEN_QUIT) == OUTCOME_WAIT
    assert worker.wait_to_quit is True
    assert worker.is_armed is False
    assert repo.get(job.id).status == "downloading"
    assert repo.get(other.id).status == "pending"
    worker.cancel_job(job.id)
    assert worker.wait_to_quit is False
    assert repo.get(job.id).status == "cancelled"
    repo.close()


def test_quit_dialog_has_exactly_three_options():
    assert QUIT_OPTION_CANCEL == "Cancel download and quit"
    assert QUIT_OPTION_PAUSE == "Pause download and quit"
    assert QUIT_OPTION_WAIT == "Wait for download to complete, then quit"


def test_gui_request_quit_uses_policy(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    job = repo.enqueue("https://example.com/g")
    repo.claim_next_pending()
    try:
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    app._ask_quit_choice = lambda: CHOICE_PAUSE_AND_QUIT
    finished = {"n": 0}
    orig_finish = app._finish_quit

    def stub_finish() -> None:
        finished["n"] += 1
        app._shutting_down = True

    app._finish_quit = stub_finish  # type: ignore[method-assign]
    try:
        app.request_quit()
        assert repo.get(job.id).status == "paused"
        assert finished["n"] == 1
    finally:
        app._finish_quit = orig_finish  # type: ignore[method-assign]
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass
