"""Tier 4.4 — per-job error detail panel."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.app import FrameForgeApp
from frameforge.upscale.guards import MIN_BLOCK_HEIGHT


def test_format_error_panel_with_and_without_error(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    ok = repo.enqueue("https://example.com/ok", title="ok")
    bad = repo.enqueue("https://example.com/bad", title="bad")
    repo.update_status(bad.id, "failed", error="Blocked: source is 4K/≥2160p (height=2160)")
    assert FrameForgeApp.format_error_panel_text(repo.get(ok.id)) == ""
    assert FrameForgeApp.format_error_panel_text(None) == ""
    text = FrameForgeApp.format_error_panel_text(repo.get(bad.id))
    assert "2160" in text
    assert "Blocked" in text
    repo.close()


def test_error_panel_updates_on_selection(tmp_path: Path):
    try:
        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert hasattr(app, "error_panel")
        ok = repo.enqueue("https://example.com/ok")
        bad = repo.enqueue("https://example.com/bad")
        block_msg = f"Blocked: source is 4K/≥2160p (height={MIN_BLOCK_HEIGHT})"
        repo.update_status(bad.id, "failed", error=block_msg)
        app.refresh_queue()

        app.queue_list.set_selected({ok.id})
        app._on_selection_changed({ok.id})
        assert app.error_panel.get("1.0", "end-1c") == ""

        app.queue_list.set_selected({bad.id})
        app._on_selection_changed({bad.id})
        shown = app.error_panel.get("1.0", "end-1c")
        assert block_msg in shown
        assert str(MIN_BLOCK_HEIGHT) in shown

        app.queue_list.set_selected(set())
        app._on_selection_changed(set())
        assert app.error_panel.get("1.0", "end-1c") == ""
    finally:
        app.destroy()
        repo.close()


def test_4k_block_reason_visible_in_panel(tmp_path: Path):
    """Tier 2 block reason remains visible through the Tier 4.4 panel."""
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    # Prefer FrameForgeApp path when possible; format helper is enough for message contract
    root.destroy()
    msg = "Blocked: source is 4K/≥2160p (height=3840)"
    repo = JobRepository(tmp_path / "b.db")
    job = repo.enqueue("https://example.com/uhd")
    repo.update_status(job.id, "failed", error=msg)
    assert "4K" in FrameForgeApp.format_error_panel_text(repo.get(job.id))
    repo.close()
