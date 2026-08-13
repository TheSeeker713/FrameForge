"""Phase F — v0.5 acceptance behaviors on the Flet UiBridge path."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi


def test_flet_retry_fail_again_increments_fail_pause(tmp_path: Path):
    repo = JobRepository(tmp_path / "acc.db")

    def boom(job, r):
        raise RuntimeError("Sign in to confirm you’re not a bot")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.02)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    first = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=a")
    second = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=b")
    worker.request_download_ids([first.id])
    deadline = time.time() + 8
    while time.time() < deadline and ui.fail_pause_shown < 1:
        time.sleep(0.03)
    assert ui.fail_pause_shown == 1
    assert worker.is_armed is False
    assert repo.get(second.id).status == "pending"
    ui.retry_failed_job(first.id)
    deadline = time.time() + 8
    while time.time() < deadline and ui.fail_pause_shown < 2:
        time.sleep(0.03)
    assert ui.fail_pause_shown == 2
    assert worker.is_armed is False
    assert repo.get(second.id).status == "pending"
    ui.shutdown()
