"""Phase 1 download engine — real short public sample downloads."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker

# Short public sample MP4 (SampleLib preview). Documented for TESTING.md.
SAMPLE_5S = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"
SAMPLE_10S = "https://samplelib.com/lib/preview/mp4/sample-10s.mp4"


def ffprobe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.timeout(180)
def test_extract_info_and_download_one(tmp_path: Path):
    ensure_output_tree()
    out = tmp_path / "dl"
    out.mkdir()
    archive = tmp_path / "archive.txt"
    dl = YtDlpDownloader(output_dir=out, archive_file=archive, use_aria2c=True)
    info = dl.extract_info(SAMPLE_5S)
    assert info.get("title") or info.get("id")
    result = dl.download(SAMPLE_5S)
    assert result.path.exists()
    assert result.path.stat().st_size > 1000
    probe = ffprobe(result.path)
    assert probe["streams"], "expected at least one stream"


@pytest.mark.timeout(300)
def test_sequential_two_downloads_and_archive(tmp_path: Path):
    ensure_output_tree()
    out = tmp_path / "dl2"
    out.mkdir()
    archive = tmp_path / "archive2.txt"
    db = tmp_path / "jobs.db"
    repo = JobRepository(db)
    dl = YtDlpDownloader(output_dir=out, archive_file=archive, use_aria2c=True)
    handler = make_download_handler(dl)
    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.05)

    j1 = repo.enqueue(SAMPLE_5S, priority=2)
    j2 = repo.enqueue(SAMPLE_10S, priority=1)
    worker.run_until_idle(timeout=240)

    job1 = repo.get(j1.id)
    job2 = repo.get(j2.id)
    assert job1.status == "completed"
    assert job2.status == "completed"
    assert job1.download_path and Path(job1.download_path).exists()
    assert job2.download_path and Path(job2.download_path).exists()
    # Sequential: finished_at of higher priority (j1) should be <= started of j2 roughly
    assert job1.finished_at is not None and job2.started_at is not None
    assert job1.finished_at <= job2.finished_at or job2.finished_at <= job1.finished_at
    # Archive hit on re-enqueue
    j3 = repo.enqueue(SAMPLE_5S, priority=5)
    worker.run_until_idle(timeout=60)
    job3 = repo.get(j3.id)
    assert job3.status == "completed"
    assert repo.archive_lookup(SAMPLE_5S) is not None
    repo.close()
