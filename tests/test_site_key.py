"""Step 1 — site_key from URL / extractor with aliases and sanitize."""

from __future__ import annotations

from types import SimpleNamespace

from frameforge.paths_site import (
    sanitize_site_key,
    site_key_from_job,
    site_key_from_url,
)


def test_youtube_watch_url():
    assert site_key_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"


def test_youtu_be():
    assert site_key_from_url("https://youtu.be/dQw4w9WgXcQ") == "youtube"


def test_x_com():
    assert site_key_from_url("https://x.com/user/status/1") == "x.com"


def test_twitter_maps_to_x():
    assert site_key_from_url("https://twitter.com/user/status/1") == "x.com"
    assert site_key_from_url("https://mobile.twitter.com/user/status/1") == "x.com"


def test_reddit():
    assert site_key_from_url("https://www.reddit.com/r/example/comments/abc/") == "reddit.com"


def test_garbage_and_empty_are_other():
    assert site_key_from_url("") == "other"
    assert site_key_from_url("   ") == "other"
    assert site_key_from_url("not a url") == "other"
    assert site_key_from_url("://") == "other"


def test_sanitize_strips_illegal_characters():
    assert "<" not in sanitize_site_key('you<>tube:"/\\|?*com')
    assert ":" not in sanitize_site_key("bad:name")
    assert sanitize_site_key("   ...  ") == "other"
    assert sanitize_site_key("") == "other"
    assert sanitize_site_key("cookies") == "other"
    assert sanitize_site_key("downloads") == "other"


def test_site_key_from_job_prefers_extractor_then_url():
    yt = SimpleNamespace(
        extractor="Youtube",
        url="https://example.com/not-youtube",
        download_path=None,
        output_path=None,
        options=lambda: {},
    )
    assert site_key_from_job(yt) == "youtube"
    tw = SimpleNamespace(
        extractor=None,
        url="https://twitter.com/a",
        download_path=None,
        output_path=None,
        options=lambda: {},
    )
    assert site_key_from_job(tw) == "x.com"
    generic = SimpleNamespace(
        extractor="generic",
        url="https://www.reddit.com/r/x",
        download_path=None,
        output_path=None,
        options=lambda: {},
    )
    assert site_key_from_job(generic) == "reddit.com"
