"""Step 4.2 — GUI import-from-browser wiring; smart-skip still works."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.cookies import (
    cookie_path_for_domain,
    has_cookies,
    should_skip_auth_prompt,
)
from tests.test_browser_cookie_import import VALID_NETSCAPE
from tests.test_tray_service import _FakeIcon

_TEST_DOMAIN = "ff-test-browser-import.example"


def test_gui_import_from_browser_handler(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "c.db")

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        dest = Path(cmd[cmd.index("--cookies") + 1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(VALID_NETSCAPE.replace("example.com", _TEST_DOMAIN), encoding="utf-8")
        return 0, "", ""

    dest = cookie_path_for_domain(_TEST_DOMAIN)
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    app._browser_cookie_runner = runner
    try:
        result = app.import_cookies_from_browser_for_site(
            f"https://{_TEST_DOMAIN}/v",
            browser="firefox",
        )
        assert result.ok is True
        assert has_cookies(_TEST_DOMAIN)
        assert should_skip_auth_prompt(_TEST_DOMAIN) is True
        app.authenticate_site(prefill=f"https://{_TEST_DOMAIN}/v")
        app.update_idletasks()
        assert app._auth_import_browser_btn.cget("text") == "Import from browser"
        assert app._auth_browser_menu.get() == "firefox"
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
        if dest.exists():
            dest.unlink()
