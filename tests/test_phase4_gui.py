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
        banner = app.seq_banner.cget("text")
        assert "press Download" in banner or "one at a time" in banner.lower()
        assert app.url_entry is not None
        assert app.import_btn is not None
        assert app.download_selected_btn is not None
        assert app.download_all_btn is not None
        assert app.worker.is_armed is False
        assert app.queue_list is not None

        assert app._default_format() == "bv*+ba/b"
        assert app._default_upscale() is True
        repo.set_setting("upscale_after_download", "0")
        assert app._default_upscale() is False

        app.refresh_queue()
        assert job.id in app.queue_list._rows
        assert ids[0] in app.queue_list._rows
        assert ids[1] in app.queue_list._rows
        assert all(repo.get(i).status == "pending" for i in ids)

        app.queue_list.set_selected({job.id})
        app._selected_ids = {job.id}
        app.cancel_selected()
        app.refresh_queue()
        assert repo.get(job.id).status == "cancelled"
        assert repo.count_by_status("downloading") <= 1
        assert app.worker.is_armed is False
    finally:
        app.destroy()
        repo.close()
