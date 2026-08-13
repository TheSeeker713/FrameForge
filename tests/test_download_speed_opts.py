"""Step 4.1 — sequential downloads still use aria2c multi-connection speed flags."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.ytdlp import YtDlpDownloader


def test_aria2c_opts_include_speed_flags():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=True)
    opts = dl.build_opts()
    assert opts["format"] == "bv*+ba/b"
    assert opts["continuedl"] is True
    assert opts["external_downloader"]["default"] == "aria2c"
    args = opts["external_downloader_args"]["aria2c"]
    joined = " ".join(args)
    assert "-x" in args and "8" in args
    assert "-s" in args
    assert "-k" in args
    assert "-c" in args
    assert "--allow-overwrite=true" in joined
    cmd = dl._build_cli_cmd("https://example.com/v")
    cli = " ".join(cmd)
    assert "--downloader" in cmd
    assert "aria2c" in cli
    assert "-x 8" in cli
    assert "-f" in cmd
    assert "bv*+ba/b" in cmd


def test_native_path_uses_concurrent_fragments():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    opts = dl.build_opts()
    assert "external_downloader" not in opts
    assert opts["concurrent_fragment_downloads"] == 8
    assert opts["format"] == "bv*+ba/b"
