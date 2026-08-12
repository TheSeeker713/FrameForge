"""Queue list unit tests without stacking multiple full GUI app sessions."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList


def test_queue_list_standalone_update(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "s.db")
        j1 = repo.enqueue("https://example.com/a", title="A")
        j2 = repo.enqueue("https://example.com/b", title="B")
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        assert j1.id in ql._rows
        assert j2.id in ql._rows
        ql.set_selected({j1.id})
        assert ql.selected_ids == {j1.id}
        repo.update_progress(j1.id, 33)
        ql.update_jobs(repo.list_jobs())
        assert j1.id in ql.selected_ids
        assert "33.0%" in ql._rows[j1.id]["label"].cget("text")
        repo.close()
    finally:
        root.destroy()
