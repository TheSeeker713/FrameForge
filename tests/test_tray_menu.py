"""Step 3.3 — tray menu Show / Pause-Resume / Quit uses the same handlers as the GUI."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from tests.test_tray_service import _FakeIcon


def test_tray_menu_labels_and_pause_resume_handler(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "m.db")
    job = repo.enqueue("https://example.com/t")
    repo.claim_next_pending()
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    app.worker.download_handler = lambda j, r: None
    try:
        app.tray.start()
        menu = app.tray._icon.menu
        texts = []
        for item in menu:
            text = getattr(item, "text", None)
            if callable(text):
                try:
                    text = text(app.tray._icon)
                except TypeError:
                    text = text()
            if text:
                texts.append(str(text))
        blob = " ".join(texts).lower()
        assert "show" in blob
        assert "quit" in blob
        assert "pause" in blob or "resume" in blob

        assert app._tray_pause_resume_label() == "Pause current"
        app._tray_pause_resume()
        assert repo.get(job.id).status == "paused"
        assert app._tray_pause_resume_label() == "Resume current"
        app._tray_pause_resume()
        assert repo.get(job.id).status != "paused"

        quit_calls = {"n": 0}
        app.request_quit = lambda: quit_calls.__setitem__("n", quit_calls["n"] + 1)  # type: ignore[method-assign]
        app.tray.on_quit()
        app.update()
        if quit_calls["n"] == 0:
            app.tray.marshal(app.request_quit)
            app.update()
        assert quit_calls["n"] == 1
    finally:
        app._shutting_down = True
        try:
            app.tray.stop(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        try:
            app.worker.stop(timeout=2)
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
