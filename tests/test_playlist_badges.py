"""Step 1.3 — playlist metadata round-trip and queue badges."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.playlist import PlaylistEntry, PlaylistListing, enqueue_selected
from frameforge.gui.queue_list import QueueList


def test_playlist_metadata_round_trip_and_filter(tmp_path: Path):
    repo = JobRepository(tmp_path / "m.db")
    listing = PlaylistListing(
        url="https://example.com/pl",
        title="Mix",
        playlist_id="PLX",
        entries=[
            PlaylistEntry(1, "https://example.com/a", title="A"),
            PlaylistEntry(2, "https://example.com/b", title="B"),
        ],
    )
    enqueue_selected(repo, listing, {1, 2})
    other = repo.enqueue("https://example.com/solo", title="solo")
    grouped = repo.list_jobs_for_playlist("PLX")
    assert [j.playlist_index for j in grouped] == [1, 2]
    assert all(j.playlist_id == "PLX" for j in grouped)
    assert other.id not in {j.id for j in grouped}
    assert grouped[0].playlist_badge == "PL 1"
    repo.close()


def test_queue_badge_shows_playlist_index(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "q.db")
        listing = PlaylistListing(
            url="https://example.com/pl",
            title="Mix",
            playlist_id="PLX",
            entries=[PlaylistEntry(4, "https://example.com/d", title="D")],
        )
        jobs = enqueue_selected(repo, listing, {4})
        ql = QueueList(root)
        ql.update_jobs(jobs)
        assert ql._badge_text(jobs[0]) == "PL 4"
        assert "PL 4" in ql._rows[jobs[0].id]["badge"].cget("text")
        repo.close()
    finally:
        root.destroy()
