"""App root: FRAMEFORGE_ROOT, then a local root file, then the profile tree."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import (
    download_dir_for_site,
    download_scan_roots,
    download_staging_dir,
    downloads_dir,
    frameforge_root,
    local_root_file,
    media_root,
)


def test_redirected_userprofile_keeps_media_on_temp_tree(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    dest = download_dir_for_site("youtube")
    assert dest == tmp_path / "Downloads" / "FrameForge" / "downloads" / "youtube" / "uncategorized"
    assert media_root() == frameforge_root()
    assert download_scan_roots() == [media_root()]
    staging = download_staging_dir(dest)
    assert staging == tmp_path / "Downloads" / "FrameForge" / "temp" / "dl"


def test_frameforge_root_env_pins_media_root(monkeypatch, tmp_path: Path):
    pinned = tmp_path / "pinned"
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(pinned))
    assert frameforge_root() == pinned
    assert media_root() == pinned
    assert download_dir_for_site("youtube") == pinned / "downloads" / "youtube" / "uncategorized"
    assert downloads_dir() == pinned / "downloads"


def test_missing_root_file_uses_profile_root(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    assert not local_root_file().exists()
    assert media_root() == frameforge_root()
    assert download_dir_for_site("pornhub.com") == frameforge_root() / "downloads" / "porn" / "uncategorized"


def test_root_file_pins_media_root(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    pinned = tmp_path / "MediaRoot"
    pinned.mkdir()
    root_file = local_root_file()
    root_file.parent.mkdir(parents=True, exist_ok=True)
    root_file.write_text(str(pinned), encoding="utf-8")
    dest = download_dir_for_site("youtube")
    assert frameforge_root() == pinned
    assert media_root() == pinned
    assert dest == pinned / "downloads" / "youtube" / "uncategorized"
    assert download_scan_roots() == [pinned]
    staging = download_staging_dir(dest)
    assert staging == pinned / "temp" / "dl"
    assert staging.is_dir()
    dl = YtDlpDownloader(output_dir=dest)
    temp = str(dl.build_opts()["paths"]["temp"]).replace("\\", "/")
    assert temp.endswith("/MediaRoot/temp/dl")


def test_paths_source_has_no_personal_folder_name():
    source = Path(__file__).resolve().parents[1] / "src" / "frameforge" / "paths.py"
    text = source.read_text(encoding="utf-8")
    assert "JEREMY" not in text
