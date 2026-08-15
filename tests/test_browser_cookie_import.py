"""Step 4.1 — yt-dlp cookies-from-browser export helper."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.browser_import import (
    BROWSER_PREFERENCE,
    CHROME_ABE_HINT,
    CHROMIUM_LOCK_HINT,
    import_cookies_from_browser,
)
from frameforge.download.cookies import NETSCAPE_HEADER, has_cookies, is_netscape_cookie_text
from frameforge.db.repository import JobRepository
from frameforge.paths import cookies_dir, ensure_output_tree

VALID_NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".example.com\tTRUE\t/\tFALSE\t0\tsession\tabc\n"
)


def test_browser_preference_firefox_first():
    assert BROWSER_PREFERENCE[0] == "firefox"
    assert "chrome" in BROWSER_PREFERENCE


def test_fake_successful_browser_export(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        dest = Path(cmd[cmd.index("--cookies") + 1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(VALID_NETSCAPE, encoding="utf-8")
        assert "--cookies-from-browser" in cmd
        assert "--skip-download" in cmd
        return 0, "ok", ""

    result = import_cookies_from_browser(
        "https://www.example.com/watch",
        browser="firefox",
        runner=runner,
    )
    assert result.ok is True
    assert result.browser == "firefox"
    assert result.path is not None
    assert result.path.parent == cookies_dir()
    assert result.path.name == "example.com.txt"
    assert has_cookies("example.com")
    assert is_netscape_cookie_text(result.path.read_text(encoding="utf-8"))


def test_validation_rejects_header_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        dest = Path(cmd[cmd.index("--cookies") + 1])
        dest.write_text(NETSCAPE_HEADER, encoding="utf-8")
        return 0, "", ""

    result = import_cookies_from_browser("example.com", browser="firefox", runner=runner)
    assert result.ok is False
    assert not has_cookies("example.com")


def test_chromium_lock_message(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        return 1, "", "Failed to decrypt cookies (DPAPI / App-Bound Encryption)"

    result = import_cookies_from_browser("example.com", browser="chrome", runner=runner)
    assert result.ok is False
    assert CHROME_ABE_HINT in result.message
    assert "App-Bound Encryption" in result.message
    assert "Firefox" in result.message
    assert "cookies.txt" in result.message
    assert "cannot be fixed by FrameForge" in result.message


def test_fail_pause_defaults_firefox_not_chrome(tmp_path: Path):
    from frameforge.errors import annotate_job_error
    from frameforge.queue.fail_pause import fail_pause_payload
    from frameforge.queue.worker import SequentialWorker
    from frameforge.ui_flet.app import FrameForgeUi
    from tests.flet_fakes import FakePage

    repo = JobRepository(tmp_path / "a.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    job = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=d")
    annotate_job_error(ui.repo, job.id, "Sign in to confirm you’re not a bot")
    dlg = ui._fail_pause_dialog(fail_pause_payload(ui.repo.get(job.id)))
    assert dlg.data["browser"].value == "firefox"
    labels = " ".join(str(getattr(a, "content", a)) for a in dlg.actions)
    assert "Firefox" in labels or "cookies.txt" in labels
    assert "Copy full report" in labels
    auth = ui.open_authenticate("https://www.youtube.com/watch?v=d")
    texts: list[str] = []

    def walk(ctrl):
        for attr in ("value", "title", "content", "label"):
            val = getattr(ctrl, attr, None)
            if isinstance(val, str):
                texts.append(val)
            elif val is not None and val is not ctrl:
                walk(val)
        for child in getattr(ctrl, "controls", None) or []:
            walk(child)

    walk(auth.content)
    blob = " ".join(texts)
    assert "Firefox" in blob
    assert "cookies.txt" in blob.lower()
    ui.shutdown()


def test_chrome_missing_profile_message(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        return 1, "", "could not find chrome cookies database"

    result = import_cookies_from_browser("example.com", browser="chrome", runner=runner)
    assert result.ok is False
    assert "Chrome not found / profile locked" in result.message


def test_auto_order_falls_through_to_edge(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    tried: list[str] = []

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        name = cmd[cmd.index("--cookies-from-browser") + 1]
        tried.append(name)
        dest = Path(cmd[cmd.index("--cookies") + 1])
        if name != "edge":
            return 1, "", "no firefox profile"
        dest.write_text(VALID_NETSCAPE, encoding="utf-8")
        return 0, "", ""

    result = import_cookies_from_browser("https://example.com/", runner=runner)
    assert tried[0] == "firefox"
    assert result.ok is True
    assert result.browser == "edge"
    assert result.path is not None
    assert result.path.parent.name == "cookies"
