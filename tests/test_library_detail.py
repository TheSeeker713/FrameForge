"""The detail panel shows the source page and every version path."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.store import LibraryStore
from frameforge.library.versions import remember_source
from frameforge.ui_flet.components.library_detail import build_library_detail
from tests.test_library import _clip, _repo


def test_detail_lists_source_url_and_both_versions(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    original = _clip(tmp_path / "clip.mp4")
    upscale = _clip(tmp_path / "clip_x4.upscaled.mp4")
    item = store.add_item(path=original, title="Clip", source="YouTube", job_id=None)
    remember_source(store, item.id, "https://www.youtube.com/watch?v=abc123xyz01")
    store.add_file(item.id, role="upscaled", path=upscale, scale=4, model="realesrgan")
    item = store.get(item.id)
    panel = build_library_detail(
        item,
        store.list_files(item.id),
        on_play=lambda _i: None,
        on_play_file=lambda _p: None,
        on_reveal=lambda _p: None,
        on_open_source=lambda _u: None,
        on_copy=lambda _t: None,
        on_rename=lambda _t: None,
    )
    assert panel.data["kind"] == "library_detail"
    assert panel.data["source_url"] == "https://www.youtube.com/watch?v=abc123xyz01"
    names = {Path(path).name for path in panel.data["paths"]}
    assert "clip.mp4" in names
    assert any(name.startswith("clip_x4") for name in names)
    assert original.is_file() and upscale.is_file()
    repo.close()
