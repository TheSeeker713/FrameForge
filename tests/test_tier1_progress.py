"""Tier 1.2 — live progress %, speed, ETA persistence and hook behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.ytdlp import (
    YtDlpDownloader,
    _format_eta,
    _format_speed,
)
from frameforge.paths import ensure_output_tree

SAMPLE = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"


def test_format_helpers():
    assert "KiB" in _format_speed(2048) or "B/s" in _format_speed(500)
    assert _format_speed(None) == "—"
    assert _format_eta(65) == "1:05"
    assert _format_eta(None) == "—"


def test_repository_stores_speed_eta(tmp_path: Path):
    repo = JobRepository(tmp_path / "prog.db")
    job = repo.enqueue("https://example.com/x")
    repo.update_progress(
        job.id,
        42.5,
        speed_bps=1024 * 50,
        eta_seconds=90,
        speed_str="50.0 KiB/s",
        eta_str="1:30",
    )
    loaded = repo.get(job.id)
    assert loaded.progress == 42.5
    opts = loaded.options()
    assert opts["speed_bps"] == 1024 * 50
    assert opts["eta_seconds"] == 90
    assert opts["speed_str"] == "50.0 KiB/s"
    assert opts["eta_str"] == "1:30"
    repo.clear_live_progress(job.id)
    opts2 = repo.get(job.id).options()
    assert opts2.get("speed_str") == "—"
    repo.close()


def test_progress_hook_emits_speed_eta_meta():
    seen: list[tuple[float, dict]] = []

    def cb(pct: float, meta: dict) -> None:
        seen.append((pct, meta))

    dl = YtDlpDownloader(use_aria2c=False)
    opts = dl.build_opts(cb)
    hook = opts["progress_hooks"][0]
    hook(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 2048.0,
            "eta": 12,
        }
    )
    assert seen
    pct, meta = seen[0]
    assert pct == 50.0
    assert meta["speed_bps"] == 2048.0
    assert meta["eta_seconds"] == 12
    assert meta["speed_str"]
    assert meta["eta_str"]


@pytest.mark.timeout(180)
def test_real_download_writes_progress(tmp_path: Path):
    ensure_output_tree()
    repo = JobRepository(tmp_path / "realprog.db")
    job = repo.enqueue(SAMPLE)
    out = tmp_path / "dl"
    out.mkdir()
    archive = tmp_path / "a.txt"
    # Native downloader for richer progress hooks
    dl = YtDlpDownloader(output_dir=out, archive_file=archive, use_aria2c=False)
    updates: list[float] = []

    def progress_cb(pct: float, meta: dict | None = None) -> None:
        updates.append(pct)
        repo.update_progress(
            job.id,
            pct,
            speed_bps=(meta or {}).get("speed_bps"),
            eta_seconds=(meta or {}).get("eta_seconds"),
            speed_str=(meta or {}).get("speed_str"),
            eta_str=(meta or {}).get("eta_str"),
        )

    repo.update_status(job.id, "downloading")
    result = dl.download(SAMPLE, progress_cb=progress_cb)
    assert result.path.exists()
    assert updates, "expected at least one progress callback"
    assert max(updates) >= 50.0 or repo.get(job.id).progress >= 50.0
    # Final clear path
    repo.update_progress(job.id, 100.0)
    repo.clear_live_progress(job.id)
    assert repo.get(job.id).progress == 100.0
    repo.close()
