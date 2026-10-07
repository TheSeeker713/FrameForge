"""Media root prefers K:\\JEREMY'S FILES\\FrameForge; tests stay isolated."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import (
    K_MEDIA_PARENT,
    download_dir_for_site,
    download_scan_roots,
    download_staging_dir,
    downloads_dir,
    frameforge_root,
    media_root,
)


def test_redirected_userprofile_keeps_media_on_temp_tree(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    dest = download_dir_for_site("youtube")
    assert dest == tmp_path / "Downloads" / "FrameForge" / "downloads" / "youtube" / "uncategorized"
    assert media_root() == frameforge_root()
    assert "JEREMY'S FILES" not in str(dest)
    assert download_scan_roots() == [media_root()]
    staging = download_staging_dir(dest)
    assert staging == tmp_path / "Downloads" / "FrameForge" / "temp" / "dl"
    assert "JEREMY'S FILES" not in str(staging)


def test_frameforge_root_env_pins_media_root(monkeypatch, tmp_path: Path):
    pinned = tmp_path / "pinned"
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(pinned))
    assert frameforge_root() == pinned
    assert media_root() == pinned
    assert download_dir_for_site("youtube") == pinned / "downloads" / "youtube" / "uncategorized"
    assert downloads_dir() == pinned / "downloads"


def test_missing_k_parent_uses_profile_root(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths.K_MEDIA_PARENT", tmp_path / "not-a-drive")
    assert not (tmp_path / "not-a-drive").exists()
    assert media_root() == frameforge_root()
    assert download_dir_for_site("pornhub.com") == frameforge_root() / "downloads" / "porn" / "uncategorized"


def test_live_profile_uses_k_when_mounted(monkeypatch):
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    if not K_MEDIA_PARENT.is_dir():
        pytest.skip(f"{K_MEDIA_PARENT} is not mounted")
    dest = download_dir_for_site("youtube")
    assert dest == K_MEDIA_PARENT / "FrameForge" / "downloads" / "youtube" / "uncategorized"
    assert frameforge_root() == dest.parent.parent.parent
    assert media_root() == frameforge_root()
    roots = download_scan_roots()
    assert roots == [dest.parent.parent.parent]
    staging = download_staging_dir(dest)
    assert staging == dest.parent.parent.parent / "temp" / "dl"
    assert staging.is_dir()
    dl = YtDlpDownloader(output_dir=dest)
    temp = str(dl.build_opts()["paths"]["temp"]).replace("\\", "/")
    assert temp.endswith("/FrameForge/temp/dl")
    assert "JEREMY'S FILES" in temp
