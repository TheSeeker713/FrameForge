"""Step 4.3 — auto-pause upscale on sustained resource pressure."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.monitor.policy import (
    PAUSE_REASON,
    MonitorSettings,
    ResourceMonitor,
    maybe_auto_pause_upscale,
)
from frameforge.monitor.sampler import ResourceReading
from frameforge.queue.worker import SequentialWorker


def test_auto_pause_sets_paused_reason_and_resume_works(tmp_path: Path):
    repo = JobRepository(tmp_path / "p.db")
    job = repo.enqueue("https://example.com/u")
    repo.claim_next_pending()
    repo.update_status(job.id, "upscaling")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    mon = ResourceMonitor(
        MonitorSettings(
            enabled=True,
            ram_warning_pct=90.0,
            cpu_warning_pct=99.0,
            sustained_seconds=0.0,
            auto_pause=True,
        )
    )
    high = ResourceReading(10.0, 95.0, 1, 2, ok=True)
    state = mon.ingest(high, now=1.0)
    assert state.warning is True
    assert state.critical is True
    assert maybe_auto_pause_upscale(worker, mon) is True
    loaded = repo.get(job.id)
    assert loaded.status == "paused"
    assert loaded.options().get("pause_reason") == PAUSE_REASON
    assert worker.is_armed is False
    resumed = worker.resume_job(job.id)
    assert resumed.status == "download_completed"
    assert resumed.upscale is True
    worker.stop(timeout=2)
    repo.close()
