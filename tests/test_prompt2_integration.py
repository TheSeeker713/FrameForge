"""Step 6.1 — Prompt 2 integration matrix (real tests)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from frameforge.convert.handler import make_convert_handler
from frameforge.db.repository import JobRepository
from frameforge.download.formats import FORMAT_PRESETS, resolve_format_selector
from frameforge.download.playlist import PlaylistEntry, PlaylistListing, enqueue_selected
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.gui.exit_policy import CHOICE_PAUSE_AND_QUIT, apply_quit_choice, classify_exit
from frameforge.gui.shortcuts import REQUIRED_ACTION_IDS, ShortcutRegistry
from frameforge.monitor.policy import (
    PAUSE_REASON,
    MonitorSettings,
    ResourceMonitor,
    maybe_auto_pause_upscale,
)
from frameforge.monitor.sampler import ResourceReading
from frameforge.paths import converted_dir, ensure_output_tree
from frameforge.queue.worker import SequentialWorker


def _clip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=48x32:rate=8:duration=0.4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return path


def test_playlist_subset_format_override_in_opts(tmp_path: Path):
    repo = JobRepository(tmp_path / "pl.db")
    listing = PlaylistListing(
        url="https://example.com/pl",
        title="Mix",
        playlist_id="PLX",
        entries=[
            PlaylistEntry(1, "https://example.com/a", title="A"),
            PlaylistEntry(2, "https://example.com/b", title="B"),
            PlaylistEntry(3, "https://example.com/c", title="C"),
        ],
    )
    jobs = enqueue_selected(
        repo, listing, {1, 3}, format_preference=FORMAT_PRESETS["≤720p"]
    )
    assert len(jobs) == 2
    assert all(j.status == "pending" for j in jobs)
    assert repo.count_by_status("downloading") == 0
    dl = YtDlpDownloader(output_dir=tmp_path / "dl")
    dl.format_preference = jobs[0].format_preference or "best"
    fmt = dl.build_opts()["format"]
    assert fmt == resolve_format_selector("≤720p")
    assert fmt != resolve_format_selector("best")
    assert jobs[0].playlist_badge
    repo.close()


def test_completed_job_converts_under_converted(tmp_path: Path):
    ensure_output_tree()
    repo = JobRepository(tmp_path / "c.db")
    clip = _clip(tmp_path / "src.mp4")
    job = repo.enqueue("https://example.com/v")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    worker.convert_handler = make_convert_handler(process_registry=worker.processes)
    worker.request_convert_ids([job.id], start_loop=False)
    assert worker._process_one() is True
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    out = Path(loaded.options()["convert_path"])
    assert out.is_file()
    assert out.stat().st_size > 0
    assert out.parent == converted_dir()
    worker.stop(timeout=2)
    repo.close()


def test_forced_resource_critical_auto_pauses_upscale(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    job = repo.enqueue("https://example.com/u")
    repo.claim_next_pending()
    repo.update_status(job.id, "upscaling")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    mon = ResourceMonitor(
        MonitorSettings(enabled=True, ram_warning_pct=90, sustained_seconds=0, auto_pause=True)
    )
    mon.ingest(ResourceReading(5.0, 96.0, 1, 2, ok=True), now=1.0)
    assert mon.state.warning is True
    assert maybe_auto_pause_upscale(worker, mon) is True
    assert repo.get(job.id).status == "paused"
    assert repo.get(job.id).options().get("pause_reason") == PAUSE_REASON
    worker.stop(timeout=2)
    repo.close()


def test_shortcut_registry_and_quit_uses_exit_policy(tmp_path: Path):
    reg = ShortcutRegistry()
    assert len(reg.action_ids()) >= len(REQUIRED_ACTION_IDS)
    assert "quit" in reg.action_ids()
    repo = JobRepository(tmp_path / "q.db")
    job = repo.enqueue("https://example.com/d")
    repo.claim_next_pending()
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert classify_exit(repo, worker) == "needs_choice"
    outcome = apply_quit_choice(worker, CHOICE_PAUSE_AND_QUIT)
    assert outcome == "exit"
    assert repo.get(job.id).status == "paused"
    worker.stop(timeout=2)
    repo.close()


def test_sequential_invariant_download_upscale_convert(tmp_path: Path):
    repo = JobRepository(tmp_path / "seq.db")
    clip = _clip(tmp_path / "m.mp4")
    conv = repo.enqueue("https://example.com/c")
    repo.update_status(conv.id, "completed", progress=100)
    repo.set_paths(conv.id, download_path=str(clip), output_path=str(clip))
    repo.queue_for_convert(conv.id)
    claimed = repo.claim_next_convert()
    assert claimed is not None
    assert claimed.status == "converting"
    pending = repo.enqueue("https://example.com/dl")
    assert repo.claim_next_pending() is None
    assert repo.get(pending.id).status == "pending"
    assert repo.claim_next_convert() is None
    assert repo.count_by_status("converting") == 1
    assert repo.count_by_status("downloading") == 0
    repo.close()
