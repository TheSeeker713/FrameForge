"""Step 3.3 — fail-pause modal actions call cookie/auth/retry with the failed job URL."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from frameforge.download.cookie_validate import clear_session_cookie_validation
from frameforge.download.cookies import cookie_path_for_url
from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from tests.test_tray_service import _FakeIcon


def test_fail_pause_actions_use_job_url(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "m.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="gated")
    annotate_job_error(repo, job.id, "Sign in to confirm you’re not a bot")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        auth_calls: list[str | None] = []
        browser_calls: list[tuple[str, str]] = []

        def fake_auth(*, prefill=None):
            auth_calls.append(prefill)

        def fake_browser(url, *, browser="firefox"):
            browser_calls.append((url, browser))
            dest = cookie_path_for_url(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tx\n",
                encoding="utf-8",
            )
            return SimpleNamespace(ok=True, message="imported")

        app.authenticate_site = fake_auth  # type: ignore[method-assign]
        app.import_cookies_from_browser_for_site = fake_browser  # type: ignore[method-assign]
        app.bridge.cookie_probe = lambda url, cookiefile: {"id": "abc", "title": "ok"}
        clear_session_cookie_validation()
        app._ask_retry_resume_after_cookies = lambda: False
        requested: list[list[int]] = []
        app.worker.request_download_ids = lambda ids: requested.append(list(ids))  # type: ignore[method-assign]
        app.worker.request_download_all = lambda: requested.append(["all"])  # type: ignore[method-assign]

        app.handle_fail_pause_action("authenticate", job.id)
        assert auth_calls == [job.url]

        app.handle_fail_pause_action("import_browser", job.id)
        assert browser_calls == [(job.url, "firefox")]
        assert repo.get(job.id).status == "failed"
        assert requested == []

        app._ask_retry_resume_after_cookies = lambda: True
        app.handle_fail_pause_action("import_browser", job.id)
        assert repo.get(job.id).status == "pending"
        assert requested == [[job.id]]
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
