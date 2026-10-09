"""Per-site download / upscale / convert directory builders under downloads/."""

from __future__ import annotations

from frameforge.paths import (
    converted_dir,
    converted_dir_for_site,
    download_dir_for_site,
    downloads_dir,
    media_root,
    upscaled_dir,
    upscaled_dir_for_site,
)


def test_download_dir_for_site_under_downloads():
    root = media_root()
    yt = download_dir_for_site("youtube")
    assert yt == root / "downloads" / "social" / "youtube" / "uncategorized"
    assert downloads_dir() in yt.parents
    xc = download_dir_for_site("x.com", "clips")
    assert xc == root / "downloads" / "social" / "x.com" / "clips"
    porn = download_dir_for_site("pornhub.com", "Squirting women.")
    assert porn == root / "downloads" / "porn" / "Squirting women"
    other = download_dir_for_site("other")
    assert other == root / "downloads" / "other" / "uncategorized"


def test_upscaled_and_converted_live_under_downloads():
    root = media_root()
    up = upscaled_dir_for_site("youtube")
    assert up.parent == upscaled_dir()
    assert upscaled_dir() == downloads_dir() / "upscaled"
    assert up.name == "youtube"
    assert str(root) in str(up)
    conv = converted_dir_for_site("pornhub.com")
    assert conv.parent == converted_dir()
    assert conv.name == "porn"
    assert "downloads" in conv.parts
    assert "converted" in conv.parts
