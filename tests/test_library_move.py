"""Library bulk move: background worker, progress, cancel, quit-safe."""

from __future__ import annotations

import inspect
import threading
import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.library.ingest import completed_jobs_not_in_library
from frameforge.library.mover import LibraryMoveRunner, run_library_move
from frameforge.library.store import LibraryStore
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.components.library import onboarding_dialog
from tests.flet_fakes import FakePage
from tests.test_library import _clip, _completed_job, _repo


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "move.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    return ui


def test_run_library_move_progress_increases(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    _completed_job(repo, _clip(tmp_path / "dl" / "a.mp4"), title="a")
    _completed_job(repo, _clip(tmp_path / "dl" / "b.mp4"), title="b", url="https://www.youtube.com/watch?v=bbbb")
    _completed_job(repo, _clip(tmp_path / "dl" / "c.mp4"), title="c", url="https://www.youtube.com/watch?v=cccc")
    ticks: list[tuple[int, int]] = []

    def on_progress(p) -> None:
        if not p.finished:
            ticks.append((p.index, p.total))

    report = run_library_move(repo, store, on_progress=on_progress)
    assert ticks == [(1, 3), (2, 3), (3, 3)]
    assert report.moved == 3
    assert report.failed == 0
    assert report.cancelled is False
    repo.close()


def test_run_library_move_cancel_stops_before_next_file(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    _completed_job(repo, _clip(tmp_path / "dl" / "a.mp4"), title="a")
    src_b = _clip(tmp_path / "dl" / "b.mp4")
    _completed_job(repo, src_b, title="b", url="https://www.youtube.com/watch?v=bbbb")
    src_c = _clip(tmp_path / "dl" / "c.mp4")
    _completed_job(repo, src_c, title="c", url="https://www.youtube.com/watch?v=cccc")
    cancel = threading.Event()
    seen = {"n": 0}

    def between(job) -> None:  # noqa: ARG001
        seen["n"] += 1
        if seen["n"] >= 2:
            cancel.set()

    report = run_library_move(repo, store, cancel=cancel, between_files=between)
    assert report.cancelled is True
    assert report.moved == 1
    assert report.skipped >= 2
    assert src_b.is_file()
    assert src_c.is_file()
    assert len(store.list_items()) == 1
    repo.close()


def test_run_library_move_progress_callback_error_does_not_abort(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    _completed_job(repo, _clip(tmp_path / "dl" / "a.mp4"), title="a")
    _completed_job(repo, _clip(tmp_path / "dl" / "b.mp4"), title="b", url="https://www.youtube.com/watch?v=bbbb")
    _completed_job(repo, _clip(tmp_path / "dl" / "c.mp4"), title="c", url="https://www.youtube.com/watch?v=cccc")

    def boom(progress) -> None:
        if progress.index == 2 and not progress.finished:
            raise RuntimeError("simulated UI/progress failure on file 2")

    report = run_library_move(repo, store, on_progress=boom)
    assert report.moved == 3
    assert report.failed == 0
    assert not (tmp_path / "dl" / "a.mp4").exists()
    assert not (tmp_path / "dl" / "b.mp4").exists()
    assert not (tmp_path / "dl" / "c.mp4").exists()
    assert len(store.list_items()) == 3
    assert report.log_path
    log_text = Path(report.log_path).read_text(encoding="utf-8")
    assert "OK" in log_text
    assert log_text.count("OK ") == 3
    repo.close()


def test_library_move_skips_part_files_and_purges_stale_rows(tmp_path: Path):
    from frameforge.library.ingest import completed_jobs_not_in_library, purge_missing_library_items

    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    gone = _clip(tmp_path / "dl" / "gone.mp4")
    job = _completed_job(repo, gone, title="gone")
    ingest_dir = store.ingest_dir()
    dest = ingest_dir / "gone.mp4"
    dest.write_bytes(b"was-here")
    store.add_item(path=dest, title="gone", job_id=job.id)
    dest.unlink()
    assert store.get_by_job_id(job.id) is not None
    gone.write_bytes(b"media-again")
    dropped = purge_missing_library_items(store)
    assert dropped == 1
    assert store.get_by_job_id(job.id) is None
    pending = completed_jobs_not_in_library(repo, store)
    assert [j.id for j in pending] == [job.id]
    part = tmp_path / "dl" / "clip.mp4.part"
    part.write_bytes(b"partial")
    report = run_library_move(repo, store, pending, extra_paths=[part])
    assert report.moved == 1
    assert report.disk_found == 0
    assert part.is_file()
    repo.close()


def test_library_move_runner_keeps_partial_report_when_callback_raises(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    ids = []
    for i, name in enumerate("abc"):
        job = _completed_job(
            repo,
            _clip(tmp_path / "dl" / f"{name}.mp4"),
            title=name,
            url=f"https://www.youtube.com/watch?v={name}{i}",
        )
        ids.append(job.id)

    def boom(progress) -> None:
        if progress.index == 2 and not progress.finished:
            raise RuntimeError("simulated UI/progress failure on file 2")

    mover = LibraryMoveRunner(repo.db_path)
    mover.start(ids, on_progress=boom)
    assert mover.join(5.0)
    assert mover.report is not None
    assert mover.report.moved == 3
    assert mover.report.failed == 0
    repo.close()


def test_run_library_move_file2_error_still_moves_file3(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    _completed_job(repo, _clip(tmp_path / "dl" / "ok1.mp4"), title="ok1")
    _completed_job(
        repo, _clip(tmp_path / "dl" / "bad.mp4"), title="bad", url="https://www.youtube.com/watch?v=bbbb"
    )
    _completed_job(repo, _clip(tmp_path / "dl" / "ok2.mp4"), title="ok2", url="https://www.youtube.com/watch?v=cccc")
    from frameforge.library import ingest as ingest_mod

    real = ingest_mod.move_into_library
    seen = {"n": 0}

    def wrap(repo, store, job, **kwargs):
        seen["n"] += 1
        if seen["n"] == 2:
            raise OSError("forced error on file 2")
        return real(repo, store, job, **kwargs)

    monkeypatch.setattr(ingest_mod, "move_into_library", wrap)
    from frameforge.library import mover as mover_mod

    monkeypatch.setattr(mover_mod, "move_into_library", wrap)
    report = run_library_move(repo, store)
    assert report.failed == 1
    assert report.moved == 2
    assert (tmp_path / "dl" / "bad.mp4").is_file()
    assert not (tmp_path / "dl" / "ok1.mp4").exists()
    assert not (tmp_path / "dl" / "ok2.mp4").exists()
    repo.close()


def test_run_library_move_continues_after_one_failure(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    _completed_job(repo, _clip(tmp_path / "dl" / "ok1.mp4"), title="ok1")
    bad = _completed_job(
        repo, _clip(tmp_path / "dl" / "gone.mp4"), title="gone", url="https://www.youtube.com/watch?v=gone"
    )
    _completed_job(repo, _clip(tmp_path / "dl" / "ok2.mp4"), title="ok2", url="https://www.youtube.com/watch?v=ok2")
    jobs = completed_jobs_not_in_library(repo, store)
    Path(bad.download_path).unlink()
    report = run_library_move(repo, store, jobs)
    assert report.failed == 1
    assert report.moved == 2
    assert report.cancelled is False
    assert len(store.list_items()) == 2
    repo.close()


def test_confirm_library_move_does_not_block_ui_thread(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    for i in range(4):
        _completed_job(
            ui.repo,
            _clip(tmp_path / "dl" / f"n{i}.mp4"),
            title=f"n{i}",
            url=f"https://www.youtube.com/watch?v=n{i:04d}",
        )
    ui.apply_library_root(tmp_path / "Lib")
    ui._library_move_hook = lambda _job: time.sleep(0.4)
    src = inspect.getsource(FrameForgeUi.confirm_library_move)
    assert "ingest_completed_jobs" not in src
    assert "shutil" not in src
    assert "LibraryMoveRunner" in src
    apply_src = inspect.getsource(FrameForgeUi._apply_move_progress)
    assert "refresh_library" not in apply_src
    assert "open_library_onboarding" not in apply_src
    t0 = time.perf_counter()
    ui.confirm_library_move()
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2
    assert ui.library_move_running
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        status = str(getattr(ui._move_status, "value", "") or "")
        if "of" in status:
            break
        time.sleep(0.01)
    assert ui._move_status is not None
    assert "Moving" in str(ui._move_status.value)
    ui.cancel_library_move()
    assert ui.wait_library_move(5.0)
    ui.shutdown()


def test_onboarding_moving_shows_progress_and_cancel():
    dlg = onboarding_dialog(
        step="move",
        root_label=r"D:\Lib",
        pending_count=47,
        sample_titles=["clip.mp4"],
        on_choose=lambda: None,
        on_move=lambda: None,
        on_skip=lambda: None,
        on_close=lambda: None,
        moving=True,
        on_cancel=lambda: None,
        progress_column=None,
        progress=(12, 47),
    )
    assert dlg.data["moving"] is True
    labels = " ".join(str(getattr(a, "content", a)) for a in dlg.actions)
    assert "Cancel" in labels
    assert "Skip" not in labels
    body = str(dlg.content)
    assert "12" in body or dlg.data["progress"] == (12, 47)


def test_quit_during_library_move_does_not_hang(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.page.window.prevent_close = True
    for i in range(3):
        _completed_job(
            ui.repo,
            _clip(tmp_path / "dl" / f"q{i}.mp4"),
            title=f"q{i}",
            url=f"https://www.youtube.com/watch?v=q{i:04d}",
        )
    ui.apply_library_root(tmp_path / "Lib")
    entered = threading.Event()

    def hook(_job) -> None:
        entered.set()
        mover = ui._library_mover
        if mover is not None:
            mover.cancel.wait(30)

    ui._library_move_hook = hook
    ui.confirm_library_move()
    assert ui.library_move_running
    assert entered.wait(2.0)
    t0 = time.perf_counter()
    ui._commit_quit()
    elapsed = time.perf_counter() - t0
    assert elapsed < 4.0
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False


def test_library_move_runner_cancel_mid_batch(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    ids = []
    for i, name in enumerate("abc"):
        job = _completed_job(
            repo,
            _clip(tmp_path / "dl" / f"{name}.mp4"),
            title=name,
            url=f"https://www.youtube.com/watch?v={name}{i}",
        )
        ids.append(job.id)
    runner = LibraryMoveRunner(repo.db_path)
    seen = {"n": 0}

    def between(job) -> None:  # noqa: ARG001
        seen["n"] += 1
        if seen["n"] >= 2:
            runner.request_cancel()

    runner.between_files = between
    runner.start(ids)
    assert runner.join(5.0)
    assert runner.report is not None
    assert runner.report.cancelled is True
    assert runner.report.moved == 1
    repo.close()


def test_migrate_includes_disk_files_without_jobs(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    job = _completed_job(repo, _clip(tmp_path / "dl" / "job.mp4"), title="job")
    loose = _clip(tmp_path / "dl" / "loose-orphan.mp4")
    ticks: list[tuple[int, int]] = []

    def on_progress(p) -> None:
        if not p.finished:
            ticks.append((p.index, p.total))

    report = run_library_move(repo, store, [job], extra_paths=[loose], on_progress=on_progress)
    assert ticks[0][1] == 2
    assert ticks[-1] == (2, 2)
    assert report.moved == 2
    assert report.disk_found == 1
    assert "disk files 1" in report.summary
    assert not loose.exists()
    assert len(store.list_items()) == 2
    repo.close()


def test_ui_move_keeps_summary_not_toast_only(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui._library_scan_roots = [tmp_path / "dl"]
    _completed_job(ui.repo, _clip(tmp_path / "dl" / "job.mp4"), title="job")
    _clip(tmp_path / "dl" / "disk-only.mp4")
    ui.apply_library_root(tmp_path / "Lib")
    ui.confirm_library_move()
    assert ui.wait_library_move(5.0)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not ui._library_move_summary:
        time.sleep(0.02)
    assert ui._library_move_summary
    assert "Moved" in ui._library_move_summary
    assert "disk files" in ui._library_move_summary
    assert ui.dialogs.kind == "library_onboard"
    dlg = ui.dialogs.current
    assert dlg is not None
    assert dlg.data.get("summary")
    labels = " ".join(str(getattr(a, "content", a)) for a in dlg.actions)
    assert "Done" in labels
    assert ui.library_visible_count == 2
    ui.dismiss_library_move_summary()
    ui.shutdown()
