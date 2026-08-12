"""Phase 4 GUI tests — single Tk session to avoid Windows Tcl multi-root flakiness."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, preview_import
from frameforge.gui.app import FrameForgeApp


def test_gui_shell_queue_settings_and_bulk(tmp_path: Path):
    repo = JobRepository(tmp_path / "gui.db")
    job = repo.enqueue("https://example.com/gui", title="gui-job", priority=2)
    repo.set_setting("format_preference", "bv*+ba/b")
    repo.set_setting("upscale_after_download", "1")

    f = tmp_path / "urls.txt"
    f.write_text("https://example.com/a.mp4\nhttps://example.com/b.mp4\n", encoding="utf-8")
    preview = preview_import(f, repo)
    assert preview.new_count == 2
    ids = confirm_add(preview, repo)

    app = FrameForgeApp(repo=repo, start_worker=False)
    try:
        app.update_idletasks()
        assert app.title() == "FrameForge"
        assert "one at a time" in app.seq_banner.cget("text").lower()
        assert app.url_entry is not None
        assert app.import_btn is not None

        assert app._default_format() == "bv*+ba/b"
        assert app._default_upscale() is True
        repo.set_setting("upscale_after_download", "0")
        assert app._default_upscale() is False

        app.refresh_queue()
        text = app.queue_box.get("1.0", "end")
        assert str(job.id) in text
        assert "gui-job" in text
        assert str(ids[0]) in text
        assert str(ids[1]) in text

        repo.cancel(job.id)
        app.refresh_queue()
        assert "cancelled" in app.queue_box.get("1.0", "end")
        assert repo.count_by_status("downloading") <= 1
    finally:
        app.destroy()
        repo.close()
