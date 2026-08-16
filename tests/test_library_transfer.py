"""Cross-volume library transfer: copy2 → verify size → unlink source."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.transfer import same_volume, transfer_file, volume_key


def test_volume_key_uses_drive_letter():
    assert volume_key(r"C:\Users\me\a.mp4") == "c:"
    assert volume_key(r"K:\JEREMY'S FILES\video\a.mp4") == "k:"
    assert same_volume(Path(r"C:\a\b.mp4"), Path(r"C:\x\y.mp4"))
    assert not same_volume(Path(r"C:\Downloads\a.mp4"), Path(r"K:\Library\a.mp4"))


def test_same_volume_tmp_is_true(tmp_path: Path):
    src = tmp_path / "a.mp4"
    dest = tmp_path / "Lib" / "a.mp4"
    src.write_bytes(b"x")
    assert same_volume(src, dest)


def test_transfer_same_volume_move(tmp_path: Path):
    src = tmp_path / "dl" / "clip.mp4"
    dest = tmp_path / "Lib" / "Uncategorized" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"media-bytes")
    out = transfer_file(src, dest)
    assert out.is_file()
    assert out.read_bytes() == b"media-bytes"
    assert not src.exists()


def test_transfer_cross_volume_copy_verify_unlink(tmp_path: Path, monkeypatch):
    from frameforge.library import transfer as t

    monkeypatch.setattr(t, "same_volume", lambda _a, _b: False)
    src = tmp_path / "dl" / "clip.mp4"
    dest = tmp_path / "Lib" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"cross-drive-payload")
    out = t.transfer_file(src, dest)
    assert out.is_file()
    assert out.read_bytes() == b"cross-drive-payload"
    assert not src.exists()


def test_transfer_rename_oserror_falls_back_to_copy(tmp_path: Path, monkeypatch):
    from frameforge.library import transfer as t

    src = tmp_path / "dl" / "clip.mp4"
    dest = tmp_path / "Lib" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"fallback-payload")

    def boom(a, b):
        raise OSError(17, "simulated EXDEV")

    monkeypatch.setattr(t.shutil, "move", boom)
    out = t.transfer_file(src, dest)
    assert out.is_file()
    assert out.read_bytes() == b"fallback-payload"
    assert not src.exists()


def test_transfer_size_mismatch_keeps_source(tmp_path: Path, monkeypatch):
    from frameforge.library import transfer as t

    monkeypatch.setattr(t, "same_volume", lambda _a, _b: False)

    def short_copy(a, b):
        Path(b).parent.mkdir(parents=True, exist_ok=True)
        Path(b).write_bytes(b"xx")

    monkeypatch.setattr(t.shutil, "copy2", short_copy)
    src = tmp_path / "dl" / "clip.mp4"
    dest = tmp_path / "Lib" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"full-payload")
    try:
        t.transfer_file(src, dest)
        raise AssertionError("expected OSError")
    except OSError as exc:
        assert "Size mismatch" in str(exc)
    assert src.is_file()
    assert src.read_bytes() == b"full-payload"
    assert not dest.exists()
