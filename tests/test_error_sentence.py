"""The job card leads with the extractor sentence, and the log keeps the warning."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.ytdlp import YtDlpDownloader, YtDlpMessageLog
from frameforge.errors import (
    EMPTY_DOWNLOAD,
    NOT_AVAILABLE,
    annotate_job_error,
    card_cause,
    extractor_sentence,
    human_cause,
)
from frameforge.ui_flet.job_view import card_view


EMPTY_WITH_WARNING = """\
yt-dlp exited with code 1
WARNING: Only images are available for download
NA
ERROR: The downloaded file is empty
"""

UNAVAILABLE = """\
yt-dlp exited with code 1
ERROR: [Eporner] yzAUyuvBAJ1: Eporner said: Video is not available
"""


def test_empty_file_is_not_the_only_sentence():
    sentence = extractor_sentence(EMPTY_WITH_WARNING)
    assert "Only images are available" in sentence
    assert "downloaded file is empty" in sentence
    assert sentence.index("Only images") < sentence.index("empty")
    shown = card_cause(sentence, human_cause(EMPTY_DOWNLOAD))
    assert shown.splitlines()[0].startswith("Only images")
    assert "empty file" in shown.lower()


def test_unavailable_sentence_leads_the_card(tmp_path: Path):
    repo = JobRepository(tmp_path / "jobs.db")
    job = repo.enqueue("https://example.com/video")
    annotate_job_error(repo, job.id, UNAVAILABLE)
    loaded = repo.get(job.id)
    opts = loaded.options()
    assert "Video is not available" in opts["error_sentence"]
    view = card_view(loaded)
    assert view["cause"].splitlines()[0].endswith("Video is not available")
    assert human_cause(NOT_AVAILABLE) in view["cause"]
    log_path = Path(opts["error_log"])
    assert log_path.is_file()
    assert "WARNING" not in log_path.read_text(encoding="utf-8") or "Video is not available" in log_path.read_text(
        encoding="utf-8"
    )
    assert "Video is not available" in log_path.read_text(encoding="utf-8")
    repo.close()


def test_capture_log_keeps_warning_and_cli_does_not_hide_it(tmp_path: Path):
    captured = YtDlpMessageLog()
    captured.warning("Only images are available for download")
    captured.error("The downloaded file is empty")
    assert captured.lines[0].startswith("WARNING:")
    assert "empty" in captured.lines[1]
    dl = YtDlpDownloader(output_dir=tmp_path, use_aria2c=False)
    cmd = dl._build_cli_cmd("https://example.com/clip")
    assert "--no-warnings" not in cmd
    assert "--quiet" not in cmd
    opts = dl.build_opts(url="https://example.com/clip")
    assert opts["no_warnings"] is False
    assert isinstance(opts["logger"], YtDlpMessageLog)
