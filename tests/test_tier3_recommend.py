"""Tier 3.2 — recommend ≤720p for upscale; mid-range allowed; ≥2160 blocked."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList
from frameforge.upscale.guards import (
    is_upscale_blocked,
    is_upscale_recommended,
)


def test_recommendation_rules():
    assert is_upscale_recommended(480) is True
    assert is_upscale_recommended(720) is True
    assert is_upscale_recommended(721) is False
    assert is_upscale_recommended(1080) is False
    assert is_upscale_recommended(2160) is False
    assert is_upscale_recommended(None) is False

    assert is_upscale_blocked(2160) is True
    assert is_upscale_blocked(4320) is True
    assert is_upscale_blocked(2159) is False
    assert is_upscale_blocked(720) is False
    assert is_upscale_blocked(None) is False


def test_job_flags_from_stored_height(tmp_path: Path):
    repo = JobRepository(tmp_path / "f.db")
    low = repo.enqueue("https://example.com/low")
    mid = repo.enqueue("https://example.com/mid")
    uhd = repo.enqueue("https://example.com/uhd")
    unk = repo.enqueue("https://example.com/unk")

    for j in (low, mid, uhd, unk):
        repo.update_status(j.id, "completed", progress=100)

    repo.set_source_resolution(low.id, 1280, 720)
    repo.set_source_resolution(mid.id, 1920, 1080)
    repo.set_source_resolution(uhd.id, 3840, 2160)

    assert repo.get(low.id).upscale_recommended is True
    assert repo.get(low.id).upscale_blocked is False
    assert repo.get(mid.id).upscale_recommended is False
    assert repo.get(mid.id).upscale_blocked is False
    assert repo.get(uhd.id).upscale_recommended is False
    assert repo.get(uhd.id).upscale_blocked is True
    assert repo.get(unk.id).upscale_recommended is False
    assert repo.get(unk.id).upscale_blocked is False
    repo.close()


def test_queue_list_recommendation_highlight_and_scroll(tmp_path: Path):
    """Single Tk root covering recommendation UI + scroll/selection survival."""
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "ui.db")
        jobs = []
        for i in range(8):
            j = repo.enqueue(f"https://example.com/{i}", title=f"t{i}", priority=i)
            repo.update_status(j.id, "completed", progress=100)
            jobs.append(j)
        low, mid, uhd = jobs[0], jobs[1], jobs[2]
        repo.set_source_resolution(low.id, 854, 480)
        repo.set_source_resolution(mid.id, 1280, 800)
        repo.set_source_resolution(uhd.id, 3840, 2160)

        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        assert low.id in ql.recommended_ids
        assert mid.id not in ql.recommended_ids
        assert uhd.id not in ql.recommended_ids
        assert "RECOMMENDED 2×" in ql._rows[low.id]["badge"].cget("text")
        assert "BLOCKED" in ql._rows[uhd.id]["badge"].cget("text")

        ql.set_selected({low.id, jobs[5].id})
        ql.restore_scroll(0.35)
        before = ql.scroll_fraction()
        for _ in range(4):
            repo.update_progress(jobs[3].id, 50)
            ql.update_jobs(repo.list_jobs())
        assert low.id in ql.recommended_ids
        assert low.id in ql.selected_ids
        assert jobs[5].id in ql.selected_ids
        after = ql.scroll_fraction()
        assert after >= 0.0
        if before > 0.05:
            assert after > 0.01
        repo.close()
    finally:
        root.destroy()
