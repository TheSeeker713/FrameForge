"""Phase 1.7 gate — bulk import + sequential worker + on-disk persistence restart."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, preview_import
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker

SAMPLE = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"
FIX = Path(__file__).parent / "fixtures"


@pytest.mark.timeout(180)
def test_phase1_gate_bulk_then_download_and_restart(tmp_path: Path):
    ensure_output_tree()
    # Custom fixture with one real sample URL
    list_file = tmp_path / "queue.txt"
    list_file.write_text(
        f"# real sample\nGate Test | {SAMPLE}\nhttps://example.com/should-skip-if-archived-later.mp4\n",
        encoding="utf-8",
    )
    db = tmp_path / "gate.db"
    out = tmp_path / "out"
    out.mkdir()
    archive = tmp_path / "arch.txt"
    repo = JobRepository(db)
    preview = preview_import(list_file, repo)
    assert preview.new_count == 2
    ids = confirm_add(preview, repo, priority=1)
    assert len(ids) == 2

    # Only download the sample URL job; cancel the example.com one to keep test fast/real
    for job in repo.list_jobs("pending"):
        if "example.com" in job.url:
            repo.cancel(job.id)

    dl = YtDlpDownloader(output_dir=out, archive_file=archive, use_aria2c=True)
    worker = SequentialWorker(repo, download_handler=make_download_handler(dl), poll_interval=0.05)
    worker.run_until_idle(timeout=120)
    done = [j for j in repo.list_jobs() if j.url == SAMPLE][0]
    assert done.status == "completed"
    assert done.download_path and Path(done.download_path).exists()
    assert repo.count_by_status("downloading") == 0
    repo.close()

    # Restart persistence
    repo2 = JobRepository(db)
    loaded = repo2.get(done.id)
    assert loaded.status == "completed"
    assert Path(loaded.download_path).exists()
    assert repo2.count_by_status("downloading") == 0
    repo2.close()
