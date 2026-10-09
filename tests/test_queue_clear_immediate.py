"""Clear from queue paints the row and undo banner before SQLite returns."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi


def _card_views(ui: FrameForgeUi) -> dict[int, dict]:
    found: dict[int, dict] = {}
    assert ui.queue_list is not None
    for card in ui.queue_list.controls:
        data = getattr(card, "data", None) or {}
        job_id = data.get("job_id")
        if job_id is None:
            continue
        found[int(job_id)] = data
    return found


def _returns_within(fn, seconds: float) -> None:
    box: dict[str, object] = {}

    def run() -> None:
        try:
            fn()
            box["ok"] = True
        except Exception as exc:  # noqa: BLE001
            box["exc"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise AssertionError(f"call still blocked after {seconds}s")
    if "exc" in box:
        raise box["exc"]  # type: ignore[misc]
    assert box.get("ok") is True


def test_clear_from_queue_drops_row_before_slow_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(tmp_path / "home"))
    db = tmp_path / "queue.db"
    repo = JobRepository(db)
    worker = SequentialWorker(repo, download_handler=lambda _job, _repo: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    keep = ui.bridge.enqueue_url("https://example.com/keep", title="keep")
    drop = ui.bridge.enqueue_url("https://example.com/drop", title="drop")
    active = ui.bridge.enqueue_url("https://example.com/active", title="active")
    ui.repo.update_status(active.id, "downloading", progress=12)
    ui.build()

    lock = sqlite3.connect(str(db), timeout=1)
    try:
        lock.execute("PRAGMA journal_mode=WAL")
        lock.execute("BEGIN IMMEDIATE")

        _returns_within(lambda: ui.handle_overflow(drop.id, "remove_from_queue"), 1.5)

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            persist = ui._persist_thread
            if persist is not None and persist.is_alive():
                break
            time.sleep(0.01)
        else:
            raise AssertionError("database clear finished while the write lock was still held")

        cards = _card_views(ui)
        assert drop.id not in cards
        assert keep.id in cards
        assert active.id in cards
        assert (cards[active.id].get("view") or {}).get("raw_status") == "downloading"
        assert ui.undo_banner is not None and ui.undo_banner.visible is True
        message = (ui.undo_banner.data or {}).get("text") or ""
        assert message == "Cleared 1 item — Undo"
        assert len(ui.bridge.clear_undo) == 1
        assert worker._thread is None
        assert worker._stop.is_set() is False

        _returns_within(lambda: ui.handle_overflow(drop.id, "remove_from_queue"), 1.5)
        assert len(ui.bridge.clear_undo) == 1
        assert (ui.undo_banner.data or {}).get("text") == "Cleared 1 item — Undo"
        assert drop.id not in _card_views(ui)
        assert keep.id in _card_views(ui)
        assert active.id in _card_views(ui)

        _returns_within(ui.undo_clear, 1.5)
        restored = _card_views(ui)
        assert drop.id in restored
        assert keep.id in restored
        assert active.id in restored
        assert ui.undo_banner.visible is False
        assert len(ui.bridge.clear_undo) == 0
    finally:
        try:
            lock.execute("COMMIT")
        except sqlite3.Error:
            pass
        lock.close()

    assert ui.wait_queue_persist(10)
    assert ui.repo.get(drop.id).queue_hidden is False
    assert ui.repo.get(keep.id).queue_hidden is False
    assert drop.id in {j.id for j in ui.repo.list_jobs()}
    assert keep.id in {j.id for j in ui.repo.list_jobs()}
    assert ui.repo.get(active.id).status == "downloading"
    assert active.id in {j.id for j in ui.repo.list_jobs()}
    ui.shutdown()
