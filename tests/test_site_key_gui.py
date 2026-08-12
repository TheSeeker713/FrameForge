"""Step 6 — queue row exposes site_key (folder name) when available."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from tests.test_tray_service import _FakeIcon


def test_job_site_key_from_url(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    yt = repo.enqueue("https://www.youtube.com/watch?v=abc", title="yt")
    xc = repo.enqueue("https://x.com/u/status/1", title="x")
    assert yt.site_key == "youtube"
    assert xc.site_key == "x.com"
    repo.close()


def test_queue_row_badge_shows_site_key(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="clip")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.refresh_queue()
        badge = app.queue_list._rows[job.id]["badge"].cget("text")
        assert "youtube" in badge
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
