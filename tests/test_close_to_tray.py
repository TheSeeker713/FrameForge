"""Step 3.2 — close-to-tray setting persists; hide does not destroy the worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from tests.test_tray_service import _FakeIcon


def test_close_to_tray_setting_persists(tmp_path: Path):
    db = tmp_path / "s.db"
    repo = JobRepository(db)
    assert repo.get_setting("close_to_tray", "0") == "0"
    repo.set_setting("close_to_tray", "1")
    repo.close()
    repo2 = JobRepository(db)
    assert repo2.get_setting("close_to_tray", "0") == "1"
    repo2.close()


def test_window_close_hides_to_tray_keeps_worker(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "t.db")
    repo.set_setting("close_to_tray", "1")
    job = repo.enqueue("https://example.com/bg")
    repo.claim_next_pending()
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    app.worker._armed.set()
    try:
        assert app._close_to_tray_enabled() is True
        app._on_window_close()
        assert app._shutting_down is False
        assert app.worker.is_armed is True
        assert repo.get(job.id).status == "downloading"
        assert app.tray.is_running is True
        assert isinstance(app.tray._icon, _FakeIcon)
        app.show_from_tray()
    finally:
        app._shutting_down = True
        try:
            app.tray.stop(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass
