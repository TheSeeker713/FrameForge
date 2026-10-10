"""Open and reveal argv for Windows, macOS, and Linux. Nothing is launched."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.actions import open_library_item_externally
from frameforge.util.reveal import open_command, reveal_command


def test_reveal_and_open_argv_for_each_platform(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    windows = reveal_command(media, platform="win32")
    assert windows == ["explorer", "/select,", str(media.resolve())]
    mac = reveal_command(media, platform="darwin")
    assert mac[:2] == ["open", "-R"]
    assert mac[2] == str(media.resolve())
    linux = reveal_command(media, platform="linux")
    assert linux[0] == "xdg-open"
    assert linux[1] == str(tmp_path.resolve())
    assert open_command(media, platform="win32")[0] == "os.startfile"
    assert open_command(media, platform="darwin")[0] == "open"
    assert open_command(media, platform="linux")[0] == "xdg-open"


def test_external_open_with_launch_off_does_not_start_a_player(tmp_path: Path):
    from frameforge.library.models import LibraryItem

    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    item = LibraryItem(
        id=1,
        job_id=None,
        title="Clip",
        source="local",
        path=str(media),
        width=None,
        height=None,
        duration=None,
        thumb_path=None,
        date_added="",
        date_modified=None,
        is_private=False,
        is_favorite=False,
        watch_later=False,
        primary_collection_id=None,
    )
    opened = open_library_item_externally(item, launch=False)
    assert opened == media.resolve()
    assert media.is_file()
