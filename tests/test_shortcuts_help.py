"""Step 5.3 — Settings/Help keyboard shortcuts listing includes every action."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.shortcuts import REQUIRED_ACTION_IDS, ShortcutRegistry
from tests.test_tray_service import _FakeIcon


def test_help_content_includes_each_registry_label(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "h.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.open_shortcuts_help()
        text = app._shortcuts_help_text
        registry = ShortcutRegistry()
        for aid in REQUIRED_ACTION_IDS:
            label = registry.label_for(aid)
            assert label in text, f"missing {aid}: {label}"
        box = app._shortcuts_help_win
        assert box is not None
        shown = app._shortcuts_help_win.children
        assert shown
    finally:
        app._shutting_down = True
        try:
            if getattr(app, "_shortcuts_help_win", None):
                app._shortcuts_help_win.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
