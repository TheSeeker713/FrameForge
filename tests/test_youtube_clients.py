"""YouTube Innertube player_client rotation on YouTube URLs only."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.youtube_clients import DEFAULT_PLAYER_CLIENTS, extractor_args_cli
from frameforge.download.ytdlp import YtDlpDownloader


def test_youtube_argv_includes_player_client():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    cmd = dl._build_cli_cmd("https://www.youtube.com/watch?v=abc")
    assert "--extractor-args" in cmd
    val = cmd[cmd.index("--extractor-args") + 1]
    assert val.startswith("youtube:player_client=")
    assert "android_vr" in val
    assert "tv_downgraded" in val
    assert "web_embedded" in val
    assert "web_safari" in val
    opts = dl.build_opts(url="https://youtu.be/abc")
    assert opts["extractor_args"]["youtube"]["player_client"][0] == "android_vr"


def test_non_youtube_argv_has_no_player_client():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--extractor-args" not in cmd
    opts = dl.build_opts(url="https://vimeo.com/123")
    assert "extractor_args" not in opts
    assert extractor_args_cli("https://example.com/v") is None


def test_settings_can_use_ytdlp_defaults(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    repo.set_setting("youtube_use_ytdlp_clients", "1")
    dl = YtDlpDownloader(output_dir=tmp_path, use_aria2c=False)
    dl._settings_repo = repo
    cmd = dl._build_cli_cmd("https://www.youtube.com/watch?v=abc")
    assert "--extractor-args" not in cmd
    repo.set_setting("youtube_use_ytdlp_clients", "0")
    repo.set_setting("youtube_player_clients", "tv_downgraded")
    cmd2 = dl._build_cli_cmd("https://www.youtube.com/watch?v=abc")
    assert cmd2[cmd2.index("--extractor-args") + 1] == "youtube:player_client=tv_downgraded"
    assert DEFAULT_PLAYER_CLIENTS
    repo.close()
