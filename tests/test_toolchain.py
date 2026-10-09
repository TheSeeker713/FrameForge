"""Download-tool setup: history skips the wizard, and a dead source is not the last try."""

from __future__ import annotations

from frameforge.setup.toolchain import (
    YTDLP_SOURCES,
    is_newer,
    launch_mode,
    notice_for,
    remote_versions,
    reset_onboarding,
    updates_needed,
)
from tests.test_library import _repo


def test_history_skips_onboarding_and_settings_can_reuse_it(tmp_path):
    repo = _repo(tmp_path)
    repo.enqueue("https://example.com/watch?v=abc")
    assert launch_mode(repo) == "check"
    assert repo.get_setting("toolchain_onboarded") == "1"
    reset_onboarding(repo)
    assert repo.get_setting("toolchain_onboarded") == "0"
    assert launch_mode(repo) == "check"
    repo.close()

    fresh_dir = tmp_path / "fresh"
    fresh_dir.mkdir()
    fresh = _repo(fresh_dir)
    assert launch_mode(fresh) == "wizard"
    fresh.close()


def test_second_source_supplies_yt_dlp_when_the_first_fails():
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        if url == YTDLP_SOURCES[0]:
            raise OSError("pypi down")
        if url == YTDLP_SOURCES[1]:
            return {"tag_name": "2026.8.19"}
        return {}

    remote = remote_versions(fetch)
    assert remote["yt-dlp"] == "2026.8.19"
    assert calls[0] == YTDLP_SOURCES[0]
    assert YTDLP_SOURCES[1] in calls
    assert len(YTDLP_SOURCES) >= 2
    needed = updates_needed({"yt-dlp": "2026.07.04", "aria2c": "1.37.0", "ffmpeg": "ok", "deno": "2.0.0"}, remote)
    assert "yt-dlp" in needed
    assert is_newer("2026.8.19", "2026.07.04")
    assert "90 days" in notice_for(["yt-dlp"], remote)
