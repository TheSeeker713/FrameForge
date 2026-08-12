"""C1 — progress updates must not rebuild the entire queue widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList
from tests.test_tray_service import _FakeIcon


def test_update_jobs_skips_repack_when_order_unchanged(tmp_path: Path):
    try:
        import customtkinter as ctk

        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "q.db")
        j1 = repo.enqueue("https://example.com/a", title="A")
        j2 = repo.enqueue("https://example.com/b", title="B")
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        assert ql._geometry_rebuilds == 1
        repo.update_progress(j1.id, 40)
        ql.update_jobs(repo.list_jobs())
        assert ql._geometry_rebuilds == 1
        assert "40.0%" in ql._rows[j1.id]["label"].cget("text")
        repo.enqueue("https://example.com/c", title="C")
        ql.update_jobs(repo.list_jobs())
        assert ql._geometry_rebuilds == 2
        assert j2.id in ql._rows
        repo.close()
    finally:
        root.destroy()


def test_update_one_job_does_not_repack(tmp_path: Path):
    try:
        import customtkinter as ctk

        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "one.db")
        job = repo.enqueue("https://example.com/a", title="A")
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        rebuilds = ql._geometry_rebuilds
        repo.update_status(job.id, "downloading", progress=12)
        loaded = repo.get(job.id)
        assert ql.update_one_job(loaded) is True
        assert ql._geometry_rebuilds == rebuilds
        assert "12.0%" in ql._rows[job.id]["label"].cget("text")
        repo.close()
    finally:
        root.destroy()


def test_refresh_progress_does_not_call_full_update_jobs(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    job = repo.enqueue("https://example.com/a", title="A")
    repo.update_status(job.id, "downloading", progress=25)
    try:
        app = FrameForgeApp(
            repo=repo, start_worker=False, tray_icon_factory=_FakeIcon
        )
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        calls = {"full": 0, "one": 0}
        orig_full = app.queue_list.update_jobs
        orig_one = app.queue_list.update_one_job

        def spy_full(jobs):
            calls["full"] += 1
            return orig_full(jobs)

        def spy_one(j):
            calls["one"] += 1
            return orig_one(j)

        app.queue_list.update_jobs = spy_full  # type: ignore[method-assign]
        app.queue_list.update_one_job = spy_one  # type: ignore[method-assign]
        app.refresh_progress()
        assert calls["full"] == 0
        assert calls["one"] == 1
        assert "25.0%" in app.progress_label.cget("text")
        assert "Downloading" in app.progress_label.cget("text")
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
