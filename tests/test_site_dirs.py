"""Step 2 — per-site download / upscale / convert directory builders."""

from __future__ import annotations

from frameforge.paths import (
    converted_dir,
    converted_dir_for_site,
    download_dir_for_site,
    frameforge_root,
    upscaled_dir,
    upscaled_dir_for_site,
)


def test_download_dir_for_site_under_root():
    root = frameforge_root()
    yt = download_dir_for_site("youtube")
    assert yt == root / "youtube"
    assert root in yt.parents or yt.parent == root
    xc = download_dir_for_site("x.com")
    assert xc.name == "x.com"
    assert str(root) in str(xc)
    other = download_dir_for_site("other")
    assert other.name == "other"
    assert other.parent == root


def test_upscaled_and_converted_include_site_segment():
    root = frameforge_root()
    up = upscaled_dir_for_site("youtube")
    assert up.parent == upscaled_dir()
    assert up.name == "youtube"
    assert str(root) in str(up)
    conv = converted_dir_for_site("x.com")
    assert conv.parent == converted_dir()
    assert conv.name == "x.com"
    assert "converted" in conv.parts
    assert "x.com" in conv.parts
