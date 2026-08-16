"""Junk triage uses Recycle Bin (unlink when recycle=False in tests)."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.junk import find_junk, move_junk, recycle_junk
from frameforge.library.store import LibraryStore
from tests.test_library import _clip, _repo


def test_find_junk_part_zero_and_orphan_json(tmp_path: Path):
    root = tmp_path / "dl"
    root.mkdir()
    (root / "clip.mp4.part").write_bytes(b"partial")
    (root / "empty.mp4").write_bytes(b"")
    (root / "clip.info.json").write_text("{}", encoding="utf-8")
    (root / "orphan.info.json").write_text("{}", encoding="utf-8")
    _clip(root / "clip.mp4", data=b"media")
    junk = find_junk([root])
    reasons = {j.reason: j.path.name for j in junk}
    assert "clip.mp4.part" in {j.path.name for j in junk}
    assert "empty.mp4" in {j.path.name for j in junk}
    assert "orphan.info.json" in {j.path.name for j in junk}
    assert "clip.info.json" not in {j.path.name for j in junk}
    assert "clip.mp4" not in {j.path.name for j in junk}
    assert "incomplete download" in reasons or any(j.reason == "incomplete download" for j in junk)
    assert any(j.reason == "zero-byte" for j in junk)
    assert any(j.reason == "orphan sidecar" for j in junk)


def test_recycle_junk_does_not_use_permanent_api_in_module():
    from frameforge.library import junk as junk_mod

    src = Path(junk_mod.__file__).read_text(encoding="utf-8")
    assert "send_to_recycle_bin" in src
    assert "os.remove" not in src
    assert "unlink(" not in src


def test_move_and_recycle_junk(tmp_path: Path):
    root = tmp_path / "dl"
    root.mkdir()
    part = root / "x.part"
    part.write_bytes(b"x")
    dest = tmp_path / "junkbox"
    moved = move_junk([part], dest)
    assert moved[0].is_file()
    assert not part.exists()
    leftover = dest / "gone.ytdl"
    leftover.write_bytes(b"y")
    recycle_junk([leftover], recycle=False)
    assert not leftover.exists()
    repo = _repo(tmp_path)
    LibraryStore(repo)
    repo.close()
