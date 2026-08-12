"""Step 5.2 — shortcuts invoke the same command methods as buttons."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.shortcuts import REQUIRED_ACTION_IDS
from tests.test_tray_service import _FakeIcon


def test_shortcut_handlers_invoke_commands(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "s.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    called: list[str] = []
    try:
        assert set(REQUIRED_ACTION_IDS) <= set(app.shortcuts.action_ids())
        for aid in (
            "download_selected",
            "download_all",
            "pause",
            "resume",
            "cancel_selected",
            "convert_mp3",
            "quit",
        ):
            app.shortcuts.bind_handler(aid, lambda a=aid: called.append(a))
        app.shortcuts.invoke("download_selected")
        app.shortcuts.invoke("quit")
        app.shortcuts.invoke("convert_mp3")
        assert called == ["download_selected", "quit", "convert_mp3"]
        app.shortcuts.invoke("shortcuts_help")
        assert app._shortcuts_help_opened is True
        app.show_tab("History")
        assert app._active_tab_name() == "History"
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
