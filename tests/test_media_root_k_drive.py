"""App root: FRAMEFORGE_ROOT, then a local root file, then the profile tree."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import (
    choose_download_location,
    download_dir_for_site,
    download_location_chosen,
    download_scan_roots,
    download_staging_dir,
    downloads_dir,
    frameforge_root,
    local_root_file,
    media_root,
    skip_download_location,
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
    # A saved download folder (this PC's K: choice) must not leak into the test.
    monkeypatch.setattr("frameforge.paths._read_download_choice", lambda: None)
    assert frameforge_root() == pinned
    assert media_root() == pinned
    assert download_dir_for_site("youtube") == pinned / "downloads" / "youtube" / "uncategorized"
    assert downloads_dir() == pinned / "downloads"


def test_missing_root_file_does_not_create_windows_downloads(monkeypatch, tmp_path: Path):
    profile = tmp_path / "profile"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    from frameforge.paths import ensure_output_tree, profile_frameforge_root

    assert not local_root_file().exists()
    pending = tmp_path / "appdata" / "FrameForge" / "pending"
    assert frameforge_root() == pending
    assert media_root() == pending
    assert download_dir_for_site("pornhub.com") == pending / "downloads" / "porn" / "uncategorized"
    ensure_output_tree()
    assert (pending / "database").is_dir()
    assert not profile_frameforge_root().exists()


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


def test_skip_download_location_uses_windows_folder(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    dest = skip_download_location()
    assert dest == tmp_path / "Downloads" / "FrameForge" / "downloads"
    assert downloads_dir() == dest
    assert download_location_chosen()
    assert download_dir_for_site("youtube") == dest / "youtube" / "uncategorized"


def test_choose_download_location_nests_under_pick(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    picked = tmp_path / "Videos"
    dest = choose_download_location(picked)
    assert dest == picked / "FrameForge" / "downloads"
    assert downloads_dir() == dest
    assert download_dir_for_site("bbc.com", "City council") == dest / "bbc.com" / "City council"
    again = choose_download_location(picked / "FrameForge")
    assert again == dest


def test_custom_download_location_does_not_create_windows_downloads(monkeypatch, tmp_path: Path):
    profile = tmp_path / "profile"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    from frameforge.paths import ensure_output_tree, profile_frameforge_root

    dest = choose_download_location(tmp_path / "Videos")
    home = tmp_path / "Videos" / "FrameForge"
    assert dest == home / "downloads"
    assert frameforge_root() == home
    ensure_output_tree()
    assert (home / "database").is_dir()
    assert (home / "models").is_dir()
    assert (home / "cookies").is_dir()
    assert not profile_frameforge_root().exists()
    assert download_scan_roots() == [home]


def test_skip_is_the_only_path_that_creates_windows_downloads(monkeypatch, tmp_path: Path):
    profile = tmp_path / "profile"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    from frameforge.paths import ensure_output_tree, profile_frameforge_root

    assert not profile_frameforge_root().exists()
    dest = skip_download_location()
    assert dest == profile / "Downloads" / "FrameForge" / "downloads"
    assert frameforge_root() == profile / "Downloads" / "FrameForge"
    ensure_output_tree()
    assert (profile / "Downloads" / "FrameForge" / "models").is_dir()


def test_paths_source_has_no_personal_folder_name():
    source = Path(__file__).resolve().parents[1] / "src" / "frameforge" / "paths.py"
    text = source.read_text(encoding="utf-8")
    assert "JEREMY" not in text
