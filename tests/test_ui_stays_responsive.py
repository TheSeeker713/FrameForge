"""The queue tick must not freeze clicks or the close button."""

from __future__ import annotations

import time
from pathlib import Path

from tests.flet_fakes import FakePage
from tests.test_ui_flet_shutdown import _ui


class LivePage(FakePage):
    """Not named FakePage, so the old refresh treated it as a real window."""


def test_tick_does_not_walk_downloads_or_extract_stills(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def _forbid_walk(*_args, **_kwargs):
        calls.append("walk")
        raise AssertionError("refresh walked the download tree")

    def _forbid_still(*_args, **_kwargs):
        calls.append("still")
        raise AssertionError("refresh extracted a thumbnail on the UI thread")

    monkeypatch.setattr("frameforge.paths.download_scan_roots", _forbid_walk)
    monkeypatch.setattr("frameforge.library.scan.download_videos_not_in_library", _forbid_walk)
    monkeypatch.setattr("frameforge.library.ingest.heal_job_download_paths", _forbid_walk)
    monkeypatch.setattr("frameforge.library.thumbs.ensure_library_thumbnail", _forbid_still)
    monkeypatch.setattr("frameforge.download.thumbnails.extract_video_still", _forbid_still)

    ui = _ui(tmp_path)
    ui.reveal_launch = False
    ui.page = LivePage()
    ui.library.complete_onboarding(tmp_path / "Lib")
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"v" * 64)
    ui.library.add_item(path=src, title="Clip")
    ui.build()
    started = time.perf_counter()
    ui.tick()
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, elapsed
    assert calls == []
    ui.tabs.selected_index = 0
    ui._on_tabs_change()
    assert ui.tabs.selected_index == 0
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    ui.shutdown()
