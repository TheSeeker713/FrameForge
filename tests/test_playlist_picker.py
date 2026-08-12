"""Step 1.2 — playlist picker enqueues a selected subset as pending jobs."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.playlist import PlaylistListing, PlaylistEntry, enqueue_selected
from frameforge.gui.playlist_picker import PlaylistPicker


def _listing() -> PlaylistListing:
    return PlaylistListing(
        url="https://example.com/pl",
        title="Demo",
        playlist_id="PLDEMO",
        entries=[
            PlaylistEntry(1, "https://example.com/a", title="A", video_id="a"),
            PlaylistEntry(2, "https://example.com/b", title="B", video_id="b"),
            PlaylistEntry(3, "https://example.com/c", title="C", video_id="c"),
        ],
        total_count=3,
    )


def test_enqueue_selected_subset_pending_only(tmp_path: Path):
    repo = JobRepository(tmp_path / "p.db")
    listing = _listing()
    jobs = enqueue_selected(repo, listing, {1, 3})
    assert len(jobs) == 2
    assert {j.url for j in jobs} == {"https://example.com/a", "https://example.com/c"}
    assert all(j.status == "pending" for j in jobs)
    assert repo.count_by_status("downloading") == 0
    urls = {j.url for j in repo.list_jobs()}
    assert "https://example.com/b" not in urls
    assert jobs[0].options().get("playlist_id") == "PLDEMO"
    repo.close()


def test_picker_select_none_then_one(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    captured: list[set[int]] = []
    try:
        picker = PlaylistPicker(root, _listing(), on_confirm=lambda s: captured.append(s))
        picker.select_none()
        assert picker.selected_indexes() == set()
        picker._vars[2].set(True)
        picker.confirm()
        assert captured == [{2}]
        repo = JobRepository(tmp_path / "g.db")
        jobs = enqueue_selected(repo, _listing(), captured[0])
        assert len(jobs) == 1
        assert jobs[0].url == "https://example.com/b"
        assert jobs[0].status == "pending"
        repo.close()
    finally:
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
