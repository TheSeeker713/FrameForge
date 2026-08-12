"""Step 1.1 — first-class paused status (distinct from cancelled/failed)."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import PAUSED_STATUS, JobRepository, TERMINAL_STATUSES
from frameforge.errors import format_error_panel
from frameforge.gui.queue_list import QueueList


def test_pending_downloading_paused_keeps_progress(tmp_path: Path):
    repo = JobRepository(tmp_path / "pause.db")
    job = repo.enqueue("https://example.com/a", title="a")
    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.status == "downloading"
    repo.update_progress(job.id, 42.5)
    repo.set_paths(job.id, download_path=str(tmp_path / "a.part"))

    paused = repo.pause(job.id)
    assert paused.status == PAUSED_STATUS
    assert paused.status == "paused"
    assert paused.progress == 42.5
    assert paused.finished_at is None
    assert paused.error is None
    assert paused.download_path == str(tmp_path / "a.part")
    assert paused.options().get("paused") is True
    assert paused.status not in TERMINAL_STATUSES
    repo.close()


def test_paused_not_claimable_until_resume(tmp_path: Path):
    repo = JobRepository(tmp_path / "hold.db")
    job = repo.enqueue("https://example.com/hold")
    assert repo.claim_next_pending() is not None
    repo.pause(job.id)
    assert repo.get(job.id).status == "paused"

    other = repo.enqueue("https://example.com/other", priority=1)
    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.id == other.id
    assert repo.get(job.id).status == "paused"

    repo.update_status(other.id, "completed", progress=100)
    assert repo.claim_next_pending() is None
    assert repo.get(job.id).status == "paused"

    resumed = repo.resume_paused(job.id)
    assert resumed.status == "pending"
    claimed2 = repo.claim_next_pending()
    assert claimed2 is not None
    assert claimed2.id == job.id
    assert claimed2.status == "downloading"
    repo.close()


def test_cancelled_is_not_paused(tmp_path: Path):
    repo = JobRepository(tmp_path / "vs.db")
    a = repo.enqueue("https://example.com/a")
    b = repo.enqueue("https://example.com/b")
    repo.claim_next_pending()
    repo.update_progress(a.id, 30)
    paused = repo.pause(a.id)
    cancelled = repo.cancel(b.id)

    assert paused.status == "paused"
    assert cancelled.status == "cancelled"
    assert paused.status != cancelled.status
    assert paused.progress == 30
    assert cancelled.progress == 0
    assert paused.finished_at is None
    assert cancelled.finished_at is not None
    assert paused.id not in {j.id for j in repo.list_history()}
    assert cancelled.id in {j.id for j in repo.list_history()}
    repo.close()


def test_pause_rejects_pending_and_cancelled(tmp_path: Path):
    repo = JobRepository(tmp_path / "rej.db")
    pending = repo.enqueue("https://example.com/p")
    with pytest.raises(ValueError, match="pending"):
        repo.pause(pending.id)
    repo.update_status(pending.id, "cancelled")
    with pytest.raises(ValueError, match="cancelled"):
        repo.pause(pending.id)
    repo.close()


def test_paused_badge_and_error_panel(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "ui.db")
        job = repo.enqueue("https://example.com/ui", title="clip")
        repo.claim_next_pending()
        repo.pause(job.id)
        loaded = repo.get(job.id)
        ql = QueueList(root)
        ql.update_jobs([loaded])
        assert ql._badge_text(loaded) == "PAUSED"
        assert "PAUSED" in ql._rows[job.id]["badge"].cget("text")
        panel = format_error_panel(loaded)
        assert "Paused" in panel
        assert "cancelled" not in panel.lower()
        repo.close()
    finally:
        root.destroy()
