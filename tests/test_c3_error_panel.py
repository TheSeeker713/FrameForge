"""C3 — error panel shows category, message, and suggested next action."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.auth_hints import AUTH_ACTION_LABEL, apply_auth_failure
from frameforge.errors import BLOCKED_4K, CANCELLED, annotate_job_error
from frameforge.gui.app import FrameForgeApp


def test_panel_auth_4k_and_cancel(tmp_path: Path):
    repo = JobRepository(tmp_path / "p.db")

    auth = repo.enqueue("https://www.youtube.com/watch?v=x", title="gated")
    apply_auth_failure(repo, auth.id, "Sign in to confirm you’re not a bot", auth.url)
    auth_text = FrameForgeApp.format_error_panel_text(repo.get(auth.id))
    assert "Category: auth_required" in auth_text
    assert "not a bot" in auth_text
    assert AUTH_ACTION_LABEL in auth_text

    blocked = repo.enqueue("https://example.com/uhd", title="uhd")
    annotate_job_error(repo, blocked.id, "Blocked: source is 4K/≥2160p (height=2160)")
    block_text = FrameForgeApp.format_error_panel_text(repo.get(blocked.id))
    assert f"Category: {BLOCKED_4K}" in block_text
    assert "2160" in block_text
    assert "lower-resolution" in block_text

    cancelled = repo.enqueue("https://example.com/c", title="c")
    repo.update_status(cancelled.id, "cancelled")
    repo.merge_options(cancelled.id, {"error_category": CANCELLED})
    cancel_text = FrameForgeApp.format_error_panel_text(repo.get(cancelled.id))
    assert f"Category: {CANCELLED}" in cancel_text
    assert "Retry" in cancel_text or "Download selected" in cancel_text

    ok = repo.enqueue("https://example.com/ok")
    assert FrameForgeApp.format_error_panel_text(repo.get(ok.id)) == ""
    repo.close()
