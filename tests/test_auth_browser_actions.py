"""Step 4.3 — auth_required error panel maps to browser import + manual authenticate."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.auth_hints import (
    AUTH_ACTION_LABEL,
    AUTH_BROWSER_IMPORT_LABEL,
    AUTH_MANUAL_LABEL,
    apply_auth_failure,
    auth_action_hint,
)
from frameforge.gui.app import FrameForgeApp
from tests.test_tray_service import _FakeIcon


def test_auth_hint_maps_browser_and_manual_actions():
    hint = auth_action_hint("https://www.youtube.com/watch?v=1")
    assert AUTH_BROWSER_IMPORT_LABEL in hint
    assert AUTH_MANUAL_LABEL in hint or AUTH_ACTION_LABEL in hint
    assert "youtube.com" in hint


def test_error_panel_auth_actions_enabled(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp as App
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "a.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=x", title="gated")
    apply_auth_failure(repo, job.id, "Sign in to confirm you’re not a bot", job.url)
    panel = FrameForgeApp.format_error_panel_text(repo.get(job.id))
    assert AUTH_BROWSER_IMPORT_LABEL in panel
    assert AUTH_ACTION_LABEL in panel

    calls: list[str] = []
    try:
        app = App(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    app._browser_cookie_runner = lambda cmd: (1, "", "no browser")
    orig_auth = app.authenticate_site
    app.authenticate_site = lambda prefill=None: calls.append(prefill or "")  # type: ignore[method-assign]
    from unittest.mock import patch

    try:
        app.queue_list.set_selected({job.id})
        app._selected_ids = {job.id}
        app._update_error_panel()
        assert str(app.import_browser_from_job_btn.cget("state")) == "normal"
        assert str(app.auth_from_job_btn.cget("state")) == "normal"
        with patch("frameforge.gui.app.messagebox.showerror"), patch(
            "frameforge.gui.app.messagebox.showinfo"
        ):
            app.import_browser_selected_job()
        assert calls == [job.url]
        app.authenticate_site = orig_auth  # type: ignore[method-assign]
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
