"""Download folders: porn bucket, social platforms, and real categories."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from frameforge.db.repository import JobRepository
from frameforge.download.handler import resolve_download_output_dir
from frameforge.layout import repair_frameforge_tree
from frameforge.paths import download_dir_for_site, downloads_dir, relocate_download_buckets
from frameforge.paths_site import category_from_metadata, site_key_from_url


def _pin(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "FrameForge"
    (root / "downloads").mkdir(parents=True)
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(root))
    monkeypatch.setattr("frameforge.paths._read_download_choice", lambda: None)
    return root


def _age(path: Path) -> None:
    old = time.time() - 7200
    os.utime(path, (old, old))


def test_eporner_resolves_to_porn_bucket(tmp_path: Path, monkeypatch):
    _pin(monkeypatch, tmp_path)
    repo = JobRepository(tmp_path / "ep.db")
    job = repo.enqueue("https://www.eporner.com/video-aaaaaaaaaaa/clip/")
    dest = resolve_download_output_dir(job)
    assert dest == download_dir_for_site("eporner.com")
    assert dest.parent.name == "porn"
    assert "eporner.com" not in dest.parts
    assert "social" not in dest.parts
    repo.close()


def test_stored_eporner_dir_remaps_to_porn(tmp_path: Path, monkeypatch):
    root = _pin(monkeypatch, tmp_path)
    stale = root / "downloads" / "eporner.com" / "uncategorized"
    stale.mkdir(parents=True)
    repo = JobRepository(tmp_path / "stale.db")
    job = repo.enqueue("https://www.eporner.com/video-bbbbbbbbbbb/clip/")
    repo.merge_options(job.id, {"download_output_dir": str(stale)})
    failed = repo.get(job.id)
    failed.status = "failed"
    dest = resolve_download_output_dir(failed)
    assert dest == downloads_dir() / "porn" / "uncategorized"
    assert not dest.parts.count("eporner.com")
    repo.close()


def test_youtube_x_and_facebook_resolve_under_social(tmp_path: Path, monkeypatch):
    _pin(monkeypatch, tmp_path)
    repo = JobRepository(tmp_path / "social.db")
    youtube = resolve_download_output_dir(repo.enqueue("https://www.youtube.com/watch?v=abcdefghijk"))
    x_com = resolve_download_output_dir(repo.enqueue("https://x.com/user/status/1"))
    facebook = resolve_download_output_dir(
        repo.enqueue("https://www.facebook.com/watch/?v=595702225249528")
    )
    assert youtube == downloads_dir() / "social" / "youtube" / "uncategorized"
    assert x_com == downloads_dir() / "social" / "x.com" / "uncategorized"
    assert facebook == downloads_dir() / "social" / "facebook" / "uncategorized"
    assert site_key_from_url("https://fb.watch/abc/") == "facebook"
    repo.close()


def test_facebook_url_is_not_kept_in_eporner(tmp_path: Path, monkeypatch):
    root = _pin(monkeypatch, tmp_path)
    stale = root / "downloads" / "eporner.com" / "uncategorized"
    stale.mkdir(parents=True)
    repo = JobRepository(tmp_path / "fb.db")
    job = repo.enqueue("https://www.facebook.com/watch/?v=595702225249528")
    repo.merge_options(
        job.id,
        {"download_output_dir": str(stale), "site_key": "eporner.com"},
    )
    loaded = repo.get(job.id)
    loaded.status = "failed"
    dest = resolve_download_output_dir(loaded)
    assert dest.parent.name == "facebook"
    assert dest.parent.parent.name == "social"
    assert "porn" not in dest.parts
    assert "eporner.com" not in dest.parts
    repo.close()


def test_previous_job_folder_is_not_reused(tmp_path: Path, monkeypatch):
    root = _pin(monkeypatch, tmp_path)
    porn_dir = root / "downloads" / "porn" / "uncategorized"
    porn_dir.mkdir(parents=True)
    repo = JobRepository(tmp_path / "reuse.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abcdefghijk")
    dest = resolve_download_output_dir(job, fallback=porn_dir)
    assert dest.parent.name == "youtube"
    assert dest.parent.parent.name == "social"
    repo.close()


def test_import_heading_is_the_category():
    chosen = category_from_metadata(
        {"categories": ["Music"], "title": "City council meeting"},
        user_category_name="Weather report",
    )
    assert chosen == "Weather report"


def test_page_metadata_replaces_uncategorized():
    assert category_from_metadata({"categories": ["News & Politics"]}) == "News & Politics"
    assert category_from_metadata({"playlist_title": "Budget hearing"}) == "Budget hearing"
    assert category_from_metadata(None, title="City council meeting") == "City council"


def test_explicit_title_stays_inside_porn(tmp_path: Path, monkeypatch):
    _pin(monkeypatch, tmp_path)
    assert category_from_metadata(None, title="Group sex clip") == "uncategorized"
    assert category_from_metadata({"categories": ["Amateur"]}, title="Group sex clip") == "Amateur"
    dest = download_dir_for_site("eporner.com", "Amateur")
    assert dest.parent.name == "porn"
    assert dest.name == "Amateur"
    plain = download_dir_for_site("eporner.com", category_from_metadata(None, title="Group sex clip"))
    assert plain == downloads_dir() / "porn" / "uncategorized"


def test_relocate_folds_eporner_and_facebook_id(tmp_path: Path, monkeypatch):
    root = _pin(monkeypatch, tmp_path)
    stale = root / "downloads" / "eporner.com" / "uncategorized"
    stale.mkdir(parents=True)
    adult = stale / "Group sex clip [o6XyMdEoOFr].mp4"
    social = stale / "Market notes [595702225249528].mp4"
    adult.write_bytes(b"adult")
    social.write_bytes(b"social")
    _age(adult)
    _age(social)
    (root / "downloads" / "youtube").mkdir()
    (root / "downloads" / "videos").mkdir()
    moved = relocate_download_buckets()
    assert not (root / "downloads" / "eporner.com").exists()
    assert (root / "downloads" / "porn" / "uncategorized" / adult.name).is_file()
    facebook = list((root / "downloads" / "social" / "facebook").rglob("*.mp4"))
    assert len(facebook) == 1
    assert facebook[0].read_bytes() == b"social"
    assert "porn" not in facebook[0].parts
    assert not (root / "downloads" / "youtube").exists()
    assert not (root / "downloads" / "videos").exists()
    assert moved


def test_repair_does_not_create_empty_videos(tmp_path: Path):
    root = tmp_path / "FrameForge"
    (root / "downloads" / "videos").mkdir(parents=True)
    repair_frameforge_tree(root)
    assert not (root / "downloads" / "videos").exists()


def test_social_url_beats_a_cached_adult_site_key():
    job = SimpleNamespace(
        extractor="Eporner",
        url="https://www.facebook.com/watch/?v=595702225249528",
        download_path=None,
        output_path=None,
        options=lambda: {"site_key": "eporner.com"},
    )
    from frameforge.paths_site import site_key_from_job

    assert site_key_from_job(job) == "facebook"
