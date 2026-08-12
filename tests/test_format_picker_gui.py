"""Step 2.2 — GUI set-format updates stored per-job preference."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.formats import FORMAT_PRESETS
from tests.test_tray_service import _FakeIcon


def test_set_format_on_job_updates_preference(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "f.db")
    job = repo.enqueue("https://example.com/x", title="x", format_preference="best")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.apply_format_to_jobs([job.id], "≤720p")
        loaded = repo.get(job.id)
        assert loaded.format_preference == FORMAT_PRESETS["≤720p"]
        app.refresh_queue()
        text = app.queue_list._rows[job.id]["label"].cget("text")
        assert "720" in text
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass
