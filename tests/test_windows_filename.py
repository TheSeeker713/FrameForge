"""A long Windows title must not fail the download when info.json is written."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.output_path import media_outtmpl, metadata_json_failed, title_trim_bytes
from frameforge.download.ytdlp import YtDlpDownloader

SCREEN_DIR = Path(r"K:\JEREMY'S FILES\FrameForge\downloads\eporner.com\uncategorized")
def test_screenshot_folder_rejects_a_200_byte_title():
    logged = "X" * (264 - len(str(SCREEN_DIR)) - 1)
    assert len(str(SCREEN_DIR / logged)) == 264
    assert len(str(SCREEN_DIR / logged)) > 259
    long_name = ("T" * 200) + " [d4d4tQL91Gu].info.json"
    assert len(str(SCREEN_DIR / long_name)) > 259


def test_template_keeps_the_infojson_path_inside_the_budget():
    budget = title_trim_bytes(SCREEN_DIR)
    assert budget > 0
    name = ("T" * budget) + " [d4d4tQL91Gu].info.json"
    assert len(str(SCREEN_DIR / name)) <= 240
    assert ".200B" not in media_outtmpl(SCREEN_DIR)


def test_deep_folder_uses_the_id_only():
    deep = Path("K:/") / ("folder " * 40)
    assert title_trim_bytes(deep) == 0
    assert media_outtmpl(deep) == "%(id)s.%(ext)s"


def test_cli_writes_infojson_by_id(tmp_path: Path):
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cmd = dl._build_cli_cmd("https://www.eporner.com/video-d4d4tQL91Gu/clip/")
    assert "infojson:%(id)s.%(ext)s" in cmd
    assert any(part.startswith("infojson:") for part in cmd)
    assert "%(title).200B" not in " ".join(cmd)


def test_metadata_write_error_is_recognized():
    assert metadata_json_failed(
        "ERROR: Cannot write video metadata to JSON file C:\\long\\name.info.json"
    )
    assert metadata_json_failed("ERROR: Video is not available") is False
