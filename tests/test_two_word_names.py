"""Filenames longer than 77 characters are saved as the first two words."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.output_path import (
    apply_two_word_name,
    install_two_word_filenames,
    two_words,
)

LONG = "alpha bravo " + ("extra " * 30)


def test_long_title_becomes_two_words():
    assert len(LONG) > 77
    assert two_words(LONG) == "alpha bravo"


def test_short_title_is_not_reduced_to_two_words():
    assert two_words("alpha bravo") == "alpha bravo"


def test_saved_file_longer_than_77_is_renamed(tmp_path: Path):
    path = tmp_path / (("word " * 20).strip() + ".mp4")
    path.write_bytes(b"ok")
    assert len(path.name) > 77
    renamed = apply_two_word_name(path)
    assert renamed.name == "word word.mp4"
    assert renamed.is_file()
    assert not path.exists()


def test_short_file_is_left_alone(tmp_path: Path):
    path = tmp_path / "short clip.mp4"
    path.write_bytes(b"ok")
    assert apply_two_word_name(path) == path
    assert path.is_file()


def test_prepare_filename_writes_two_words(tmp_path: Path):
    install_two_word_filenames()
    from yt_dlp import YoutubeDL

    ydl = YoutubeDL(
        {
            "quiet": True,
            "noprogress": True,
            "outtmpl": {"default": "%(title).200B [%(id)s].%(ext)s"},
            "paths": {"home": str(tmp_path)},
        }
    )
    prepared = Path(
        ydl.prepare_filename(
            {"title": LONG, "id": "abc123", "ext": "mp4"},
        )
    )
    assert prepared.name == "alpha bravo.mp4"
    assert len(prepared.name) <= 77
