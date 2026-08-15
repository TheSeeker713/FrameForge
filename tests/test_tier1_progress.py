"""Tier 1.2 — live progress %, speed, ETA persistence and hook behavior."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.ytdlp import (
    YtDlpDownloader,
    _format_eta,
    _format_speed,
    parse_cli_progress_line,
)
from frameforge.paths import ensure_output_tree
from frameforge.queue.process_registry import ProcessRegistry

SAMPLE = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"
SAMPLE_10S = "https://samplelib.com/lib/preview/mp4/sample-10s.mp4"


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


def test_parse_ytdlp_progress_line_speed_and_eta():
    parsed = parse_cli_progress_line(
        "[download]  42.5% of  10.50MiB at  512.00KiB/s ETA 00:19"
    )
    assert parsed is not None
    assert parsed["percent"] == 42.5
    assert parsed["speed_bps"] is not None
    assert abs(parsed["speed_bps"] - 512.0 * 1024) < 1.0
    assert parsed["eta_seconds"] == 19.0
    assert parsed["speed_str"] != "—"
    assert parsed["eta_str"] != "—"
    assert "KiB" in parsed["speed_str"] or "B/s" in parsed["speed_str"]
    assert parsed["eta_str"] == "0:19"


def test_parse_ytdlp_progress_line_hours_eta_and_finished_speed():
    live = parse_cli_progress_line(
        "[download]   5.0% of ~  50.00MiB at    1.20MiB/s ETA 01:05:00 (frag 2/16)"
    )
    assert live is not None
    assert live["percent"] == 5.0
    assert live["eta_seconds"] == 3900.0
    assert live["eta_str"] == "1:05:00"
    assert live["speed_bps"] is not None
    assert live["speed_str"] != "—"

    done = parse_cli_progress_line(
        "[download] 100% of  3.21MiB in 00:04 at 800.00KiB/s"
    )
    assert done is not None
    assert done["percent"] == 100.0
    assert done["speed_bps"] is not None
    assert done["speed_str"] != "—"


def test_parse_aria2c_progress_line():
    parsed = parse_cli_progress_line(
        "[#1 SIZE:1.23MiB/10.50MiB(11%) CN:8 DL:512KiB/s ETA:18s]"
    )
    assert parsed is not None
    assert parsed["percent"] == 11.0
    assert parsed["speed_bps"] is not None
    assert abs(parsed["speed_bps"] - 512.0 * 1024) < 1.0
    assert parsed["eta_seconds"] == 18.0
    assert parsed["speed_str"] != "—"
    assert parsed["eta_str"] == "0:18"

    spd = parse_cli_progress_line(
        "[#1 SIZE:2.0MiB/8.0MiB(25%) CN:4 SPD:1.5MiB/s ETA:1m12s]"
    )
    assert spd is not None
    assert spd["percent"] == 25.0
    assert spd["eta_seconds"] == 72.0
    assert spd["speed_str"] != "—"

    compact = parse_cli_progress_line(
        "[#51d556 576KiB/5.2MiB(10%) CN:1 DL:1.1MiB ETA:3s]"
    )
    assert compact is not None
    assert compact["percent"] == 10.0
    assert compact["eta_seconds"] == 3.0
    assert compact["speed_bps"] is not None
    assert compact["speed_str"] != "—"

    done = parse_cli_progress_line(
        "[download] 100% of    5.23MiB in 00:00:02 at 1.77MiB/s"
    )
    assert done is not None
    assert done["percent"] == 100.0
    assert done["speed_str"] != "—"
    assert done["speed_bps"] is not None


def test_parse_cli_progress_ignores_non_progress():
    assert parse_cli_progress_line("[download] Destination: clip.mp4") is None
    assert parse_cli_progress_line("https://example.com/100%_off") is None
    assert parse_cli_progress_line("") is None
    unknown = parse_cli_progress_line(
        "[download]   0.0% of  1.00MiB at  Unknown B/s ETA Unknown"
    )
    assert unknown is not None
    assert unknown["percent"] == 0.0
    assert unknown["speed_str"] == "—"
    assert unknown["eta_str"] == "—"


def test_parse_aria2_size_without_percent():
    parsed = parse_cli_progress_line(
        "[#1 SIZE:512MiB/1.0GiB CN:16 DL:3.1MiB ETA:2m30s]"
    )
    assert parsed is not None
    assert parsed["percent"] > 45
    assert parsed["percent"] < 55
    assert parsed["speed_str"] != "—"
    assert parsed["eta_seconds"] == 150.0


def _is_live_speed_or_eta(meta: dict) -> bool:
    speed = meta.get("speed_str")
    eta = meta.get("eta_str")
    speed_ok = bool(speed) and speed != "—"
    eta_ok = bool(eta) and eta not in ("—", "00:00", "0:00")
    return speed_ok or eta_ok


@pytest.mark.timeout(180)
def test_subprocess_download_emits_speed_or_eta(tmp_path: Path):
    """Killable CLI path must persist real speed/ETA, not placeholders only."""
    ensure_output_tree()
    repo = JobRepository(tmp_path / "subprog.db")
    job = repo.enqueue(SAMPLE_10S)
    out = tmp_path / "dl"
    out.mkdir()
    archive = tmp_path / "a.txt"
    dl = YtDlpDownloader(output_dir=out, archive_file=archive, use_aria2c=True)
    registry = ProcessRegistry()
    metas: list[dict] = []
    pcts: list[float] = []

    def progress_cb(pct: float, meta: dict | None = None) -> None:
        pcts.append(pct)
        meta = dict(meta or {})
        metas.append(meta)
        repo.update_progress(
            job.id,
            pct,
            speed_bps=meta.get("speed_bps"),
            eta_seconds=meta.get("eta_seconds"),
            speed_str=meta.get("speed_str"),
            eta_str=meta.get("eta_str"),
        )

    repo.update_status(job.id, "downloading")
    result = dl.download(
        SAMPLE_10S,
        progress_cb=progress_cb,
        job_id=job.id,
        process_registry=registry,
    )
    assert result.path.exists()
    assert pcts, "expected at least one subprocess progress callback"
    live = [m for m in metas if _is_live_speed_or_eta(m)]
    assert live, f"expected non-placeholder speed/ETA from subprocess path, got {metas!r}"
    assert registry.pid_for(job.id) is None
    assert repo.count_by_status("downloading") <= 1
    repo.close()


@pytest.mark.timeout(180)
@pytest.mark.filterwarnings(
    "ignore:Exception ignored in:pytest.PytestUnraisableExceptionWarning"
)
def test_subprocess_progress_persists_via_handler(tmp_path: Path):
    """Worker download handler + killable subprocess writes speed/ETA to SQLite.

    Isolation: earlier CustomTkinter tests can leave Tk ``Variable`` objects.
    If those finalize on the worker thread, pytest emits an unraisable
    ``main thread is not in main loop``. Collect on the main thread first.
    The warning filter is this test only — it does not hide assertion failures.
    """
    import gc

    gc.collect()
    from frameforge.download.handler import make_download_handler
    from frameforge.queue.worker import SequentialWorker

    ensure_output_tree()
    repo = JobRepository(tmp_path / "hprog.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(
        output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True
    )
    saw_live: list[dict] = []
    orig = repo.update_progress

    def spy(
        job_id: int,
        progress: float,
        *,
        speed_bps: float | None = None,
        eta_seconds: float | None = None,
        speed_str: str | None = None,
        eta_str: str | None = None,
    ) -> None:
        orig(
            job_id,
            progress,
            speed_bps=speed_bps,
            eta_seconds=eta_seconds,
            speed_str=speed_str,
            eta_str=eta_str,
        )
        if _is_live_speed_or_eta({"speed_str": speed_str, "eta_str": eta_str}):
            saw_live.append({"speed_str": speed_str, "eta_str": eta_str, "progress": progress})

    repo.update_progress = spy  # type: ignore[method-assign]
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    worker.download_handler = make_download_handler(dl, process_registry=worker.processes)
    job = repo.enqueue(SAMPLE_10S)
    worker.request_download_ids([job.id])

    deadline = time.time() + 180
    while time.time() < deadline:
        assert repo.count_by_status("downloading") <= 1
        loaded = repo.get(job.id)
        if loaded.status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)

    assert repo.get(job.id).status == "completed", repo.get(job.id).error
    assert saw_live, "handler never persisted non-placeholder speed/ETA"
    worker.stop(timeout=5)
    repo.close()
    gc.collect()
