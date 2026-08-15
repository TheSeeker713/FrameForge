"""v0.5.9 — recover download_path after yt-dlp exit 0; output_missing not auth."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.output_path import (
    OutputMissingError,
    require_download_artifact,
    resolve_download_artifact,
    video_id_from_url,
)
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.errors import AUTH_REQUIRED, OUTPUT_MISSING, UNKNOWN, classify_error, should_fail_pause
from frameforge.queue.fail_pause import fail_pause_payload, maybe_fail_pause, modal_actions_for
from frameforge.queue.worker import SequentialWorker


def test_video_id_from_youtube_url():
    assert video_id_from_url("https://www.youtube.com/watch?v=Zy7EXDONlTY") == "Zy7EXDONlTY"
    assert video_id_from_url("https://youtu.be/Zy7EXDONlTY") == "Zy7EXDONlTY"


def test_exit_0_recovers_sanitized_name_with_id(tmp_path: Path):
    video_id = "Zy7EXDONlTY"
    url = f"https://www.youtube.com/watch?v={video_id}"
    missing = tmp_path / "Look at this [Official] emoji.mp4"
    actual = tmp_path / f"Look at this - Official - {video_id}.mp4"
    actual.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
    resolved = resolve_download_artifact(
        url=url,
        output_dir=tmp_path,
        printed=[str(missing), "Look at this", "youtube", video_id],
    )
    assert resolved.path == actual.resolve()
    assert resolved.recovery_method == "glob_id"
    found = require_download_artifact(
        url=url,
        output_dir=tmp_path,
        printed=[str(missing)],
    )
    assert found.path == actual.resolve()


def test_exit_0_archive_hit_no_file_is_output_missing(tmp_path: Path):
    video_id = "Zy7EXDONlTY"
    url = f"https://www.youtube.com/watch?v={video_id}"
    archive = tmp_path / "ytdlp-archive.txt"
    archive.write_text(f"youtube {video_id}\n", encoding="utf-8")
    try:
        require_download_artifact(
            url=url,
            output_dir=tmp_path,
            printed=["NA"],
            output_tail=["[download] Zy7EXDONlTY has already been recorded in the archive"],
            archive_file=archive,
        )
        raise AssertionError("expected OutputMissingError")
    except OutputMissingError as exc:
        assert exc.archive_hit is True
        assert "Archive lists this video" in str(exc)
    assert classify_error(str(OutputMissingError(url, archive_hit=True))) == OUTPUT_MISSING
    assert classify_error(str(OutputMissingError(url, archive_hit=True))) != AUTH_REQUIRED
    assert classify_error(str(OutputMissingError(url, archive_hit=True))) != UNKNOWN
    assert should_fail_pause(OUTPUT_MISSING) is True
    ids = [a[0] for a in modal_actions_for(OUTPUT_MISSING, archive_hit=True)]
    assert ids[0] == "retry"
    assert "import_browser" not in ids
    assert "authenticate" not in ids
    assert "open_folder" in ids


def test_exit_0_no_file_is_output_missing_not_unknown(tmp_path: Path):
    url = "https://www.youtube.com/watch?v=Zy7EXDONlTY"
    try:
        require_download_artifact(url=url, output_dir=tmp_path, printed=["NA"])
        raise AssertionError("expected OutputMissingError")
    except OutputMissingError as exc:
        assert exc.archive_hit is False
        assert "Downloaded file not found" in str(exc)
    assert classify_error(f"Downloaded file not found for {url}") == OUTPUT_MISSING
    assert classify_error(f"Downloaded file not found for {url}") != UNKNOWN
    assert classify_error(f"Downloaded file not found for {url}") != AUTH_REQUIRED


def test_cli_omits_archive_when_force_redownload(tmp_path: Path):
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--download-archive" in cmd
    dl.ignore_download_archive = True
    cmd2 = dl._build_cli_cmd("https://example.com/v")
    assert "--download-archive" not in cmd2


def test_fail_pause_output_missing_not_cookie_primary(tmp_path: Path):
    repo = JobRepository(tmp_path / "o.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=Zy7EXDONlTY")
    from frameforge.errors import annotate_job_error

    annotate_job_error(
        repo, job.id, "Archive lists this video but the file is missing on disk."
    )
    loaded = repo.get(job.id)
    assert loaded.options().get("error_category") == OUTPUT_MISSING
    assert loaded.options().get("force_redownload") is True
    payload = fail_pause_payload(loaded)
    ids = [b["id"] for b in payload["buttons"]]
    assert ids[0] == "retry"
    assert "import_browser" not in ids
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert maybe_fail_pause(worker, repo, loaded) is True
    repo.close()
