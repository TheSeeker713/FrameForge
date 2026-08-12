"""Step 1.1 — playlist detect + flat extract (no auto-enqueue)."""

from __future__ import annotations

from frameforge.download.playlist import (
    PLAYLIST_ENTRY_CAP,
    extract_playlist,
    looks_like_playlist_info,
    looks_like_playlist_url,
    parse_flat_listing,
)


def test_single_video_info_is_not_playlist():
    info = {
        "_type": "video",
        "id": "abc",
        "title": "One clip",
        "webpage_url": "https://example.com/v/abc",
    }
    assert looks_like_playlist_info(info) is False
    assert parse_flat_listing("https://example.com/v/abc", info) is None


def test_flat_playlist_entries_and_indexes():
    info = {
        "_type": "playlist",
        "id": "PL1",
        "title": "Demo list",
        "playlist_count": 3,
        "entries": [
            {
                "id": "a",
                "title": "First",
                "url": "https://example.com/a",
                "playlist_index": 1,
            },
            {
                "id": "b",
                "title": "Second",
                "webpage_url": "https://example.com/b",
                "playlist_index": 2,
            },
            {"id": "c", "title": "Third", "url": "c", "ie_key": "Youtube", "playlist_index": 3},
        ],
    }
    listing = parse_flat_listing("https://example.com/playlist?list=PL1", info)
    assert listing is not None
    assert listing.playlist_id == "PL1"
    assert listing.title == "Demo list"
    assert len(listing.entries) == 3
    assert listing.entries[0].url == "https://example.com/a"
    assert listing.entries[1].url == "https://example.com/b"
    assert listing.entries[2].url == "https://www.youtube.com/watch?v=c"
    assert [e.index for e in listing.entries] == [1, 2, 3]
    assert listing.truncated is False


def test_playlist_cap_truncates():
    entries = [
        {"id": str(i), "title": f"t{i}", "url": f"https://example.com/{i}", "playlist_index": i}
        for i in range(1, 12)
    ]
    info = {"_type": "playlist", "id": "big", "title": "Big", "entries": entries, "playlist_count": 11}
    listing = parse_flat_listing("https://example.com/pl", info, cap=5)
    assert listing is not None
    assert len(listing.entries) == 5
    assert listing.truncated is True
    assert listing.total_count == 11
    assert PLAYLIST_ENTRY_CAP >= 5


def test_extract_playlist_uses_injected_extractor():
    def fake(_url: str) -> dict:
        return {
            "_type": "playlist",
            "id": "X",
            "title": "Injected",
            "entries": [
                {"id": "1", "title": "A", "url": "https://example.com/1", "playlist_index": 1},
                {"id": "2", "title": "B", "url": "https://example.com/2", "playlist_index": 2},
            ],
        }

    listing = extract_playlist("https://example.com/pl", extract_fn=fake)
    assert listing is not None
    assert [e.title for e in listing.entries] == ["A", "B"]

    def single(_url: str) -> dict:
        return {"_type": "video", "id": "z", "title": "Solo"}

    assert extract_playlist("https://example.com/v", extract_fn=single) is None


def test_playlist_url_heuristic():
    assert looks_like_playlist_url("https://www.youtube.com/playlist?list=PLabc")
    assert looks_like_playlist_url("https://www.youtube.com/watch?v=x&list=PLabc")
    assert looks_like_playlist_url("https://example.com/v/x") is False
