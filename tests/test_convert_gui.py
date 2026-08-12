"""Step 3.3 — Convert to MP3 button eligibility and ffmpeg error panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.errors import FFMPEG, annotate_job_error
from frameforge.gui.app import FrameForgeApp
from tests.test_tray_service import _FakeIcon


def test_convert_error_panel_shows_ffmpeg_category(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    job = repo.enqueue("https://example.com/c", title="clip")
    annotate_job_error(repo, job.id, "ffmpeg: input not found: missing.mp4")
    text = FrameForgeApp.format_error_panel_text(repo.get(job.id))
    assert f"Category: {FFMPEG}" in text
    assert "input not found" in text
    repo.close()


def test_convert_button_enabled_only_when_eligible(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp as App
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    pending = repo.enqueue("https://example.com/p", title="pending")
    done = repo.enqueue("https://example.com/d", title="done")
    clip = tmp_path / "ok.mp4"
    clip.write_bytes(b"not-a-real-video-but-file-exists")
    repo.update_status(done.id, "completed", progress=100)
    repo.set_paths(done.id, download_path=str(clip), output_path=str(clip))
    try:
        app = App(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.refresh_queue()
        app.queue_list.set_selected({pending.id})
        app._on_queue_selection_changed({pending.id})
        assert str(app.convert_mp3_btn.cget("state")) == "disabled"

        app.queue_list.set_selected({done.id})
        app._on_queue_selection_changed({done.id})
        assert str(app.convert_mp3_btn.cget("state")) == "normal"

        # Ineligible convert_selected does not crash
        shown: list[str] = []

        def _info(title, msg):
            shown.append(str(msg))

        import frameforge.gui.app as app_mod

        orig = app_mod.messagebox.showinfo
        app_mod.messagebox.showinfo = _info  # type: ignore[method-assign]
        try:
            app.queue_list.set_selected({pending.id})
            app._on_queue_selection_changed({pending.id})
            app.convert_selected()
            assert repo.get(pending.id).status == "pending"
            assert shown
        finally:
            app_mod.messagebox.showinfo = orig
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass
