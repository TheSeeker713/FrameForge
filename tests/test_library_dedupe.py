"""Duplicate detection by normalized title + size + duration."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.dedupe import (
    find_duplicate_groups,
    merge_duplicate_groups,
    normalize_title,
    pick_keeper,
)
from frameforge.library.store import LibraryStore
from tests.test_library import _clip, _repo


def test_normalize_title_strips_bracket_ids():
    assert normalize_title("Song Title [dQw4w9WgXcQ]") == "song title"
    assert normalize_title("Song Title [abc] [1080p]", path="x.mp4") == "song title"
    assert normalize_title("Song Title") == "song title"


def test_merge_duplicates_recycles_extra(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    home = store.complete_onboarding(tmp_path / "Lib")
    a = _clip(home / "Uncategorized" / "Song Title [aaaaaa].mp4", data=b"same-bytes")
    b = _clip(home / "Uncategorized" / "Song Title [bbbbbb].mp4", data=b"same-bytes")
    store.add_item(path=a, title="Song Title [aaaaaa]", duration=12.5, height=720)
    newer = store.add_item(path=b, title="Song Title [bbbbbb]", duration=12.5, height=1080)
    groups = find_duplicate_groups(store)
    assert len(groups) == 1
    assert pick_keeper(groups[0].items).id == newer.id
    report = merge_duplicate_groups(store, groups, recycle=False)
    assert report.recycled == 1
    assert report.kept == 1
    left = store.list_items()
    assert len(left) == 1
    assert left[0].id == newer.id
    assert Path(left[0].path).is_file()
    assert not a.exists()
    repo.close()
