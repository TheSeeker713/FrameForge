"""Step 1.1 — clear selected jobs from the live queue without deleting media."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository


def test_clear_selected_removes_only_those_rows(tmp_path: Path):
    repo = JobRepository(tmp_path / "q.db")
    keep_pending = repo.enqueue("https://example.com/keep-p", title="keep-p")
    drop_pending = repo.enqueue("https://example.com/drop-p", title="drop-p")
    keep_done = repo.enqueue("https://example.com/keep-d", title="keep-d")
    drop_done = repo.enqueue("https://example.com/drop-d", title="drop-d")
    repo.update_status(keep_done.id, "completed", progress=100)
    repo.update_status(drop_done.id, "completed", progress=100)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake")
    repo.set_paths(drop_done.id, download_path=str(media), output_path=str(media))

    cleared = repo.clear_from_queue([drop_pending.id, drop_done.id])
    assert set(cleared) == {drop_pending.id, drop_done.id}

    visible_ids = {j.id for j in repo.list_jobs()}
    assert keep_pending.id in visible_ids
    assert keep_done.id in visible_ids
    assert drop_pending.id not in visible_ids
    assert drop_done.id not in visible_ids

    # Pending row is gone; completed row remains for history
    try:
        repo.get(drop_pending.id)
        assert False, "pending row should be hard-deleted"
    except KeyError:
        pass
    hidden = repo.get(drop_done.id)
    assert hidden.status == "completed"
    assert hidden.queue_hidden is True
    assert hidden.id in {j.id for j in repo.list_history()}
    assert media.is_file()
    repo.close()


def test_clear_selected_skips_active_download(tmp_path: Path):
    repo = JobRepository(tmp_path / "a.db")
    pending = repo.enqueue("https://example.com/p")
    active = repo.enqueue("https://example.com/dl")
    repo.update_status(active.id, "downloading", progress=10)
    cleared = repo.clear_from_queue([pending.id, active.id])
    assert cleared == [pending.id]
    assert repo.get(active.id).status == "downloading"
    assert active.id in {j.id for j in repo.list_jobs()}
    repo.close()
