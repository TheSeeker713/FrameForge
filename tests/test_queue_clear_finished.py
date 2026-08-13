"""Step 1.2 — clear completed / failed / finished from the live queue."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository


def _seed(tmp_path: Path) -> tuple[JobRepository, dict[str, int]]:
    repo = JobRepository(tmp_path / "f.db")
    ids: dict[str, int] = {}
    ids["pending"] = repo.enqueue("https://example.com/p").id
    ids["paused"] = repo.enqueue("https://example.com/z").id
    repo.update_status(ids["paused"], "downloading", progress=5)
    repo.pause(ids["paused"])
    ids["downloading"] = repo.enqueue("https://example.com/dl").id
    repo.update_status(ids["downloading"], "downloading", progress=20)
    ids["completed"] = repo.enqueue("https://example.com/ok").id
    repo.update_status(ids["completed"], "completed", progress=100)
    ids["failed"] = repo.enqueue("https://example.com/bad").id
    repo.update_status(ids["failed"], "failed", error="nope")
    ids["cancelled"] = repo.enqueue("https://example.com/c").id
    repo.update_status(ids["cancelled"], "cancelled")
    return repo, ids


def test_clear_completed_leaves_others(tmp_path: Path):
    repo, ids = _seed(tmp_path)
    cleared = repo.clear_completed_from_queue()
    assert cleared == [ids["completed"]]
    visible = {j.id: j.status for j in repo.list_jobs()}
    assert ids["completed"] not in visible
    assert visible[ids["pending"]] == "pending"
    assert visible[ids["paused"]] == "paused"
    assert visible[ids["downloading"]] == "downloading"
    assert visible[ids["failed"]] == "failed"
    assert visible[ids["cancelled"]] == "cancelled"
    assert repo.get(ids["completed"]).queue_hidden is True
    repo.close()


def test_clear_failed_leaves_others(tmp_path: Path):
    repo, ids = _seed(tmp_path)
    cleared = repo.clear_failed_from_queue()
    assert cleared == [ids["failed"]]
    visible = {j.id for j in repo.list_jobs()}
    assert ids["failed"] not in visible
    assert ids["completed"] in visible
    assert ids["pending"] in visible
    repo.close()


def test_clear_finished_hides_completed_failed_cancelled(tmp_path: Path):
    repo, ids = _seed(tmp_path)
    cleared = repo.clear_finished_from_queue()
    assert set(cleared) == {ids["completed"], ids["failed"], ids["cancelled"]}
    visible = {j.id: j.status for j in repo.list_jobs()}
    assert ids["pending"] in visible
    assert ids["paused"] in visible
    assert ids["downloading"] in visible
    assert ids["completed"] not in visible
    assert ids["failed"] not in visible
    assert ids["cancelled"] not in visible
    hist_ids = {j.id for j in repo.list_history()}
    assert ids["completed"] in hist_ids
    assert ids["failed"] in hist_ids
    assert ids["cancelled"] in hist_ids
    repo.close()
