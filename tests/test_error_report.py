"""Copy full error report includes category, stderr, argv, version."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.error_report import format_full_error_report
from frameforge.errors import annotate_job_error
from frameforge.queue.fail_pause import fail_pause_payload
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage


def test_format_full_error_report_synthetic_failure(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="clip")
    annotate_job_error(repo, job.id, "yt-dlp exited with code 1\nno stderr; see invocation log")
    repo.merge_options(
        job.id,
        {
            "ytdlp_invocation": {
                "argv": ["python", "-m", "yt_dlp", "-f", "bv*+ba/b", "https://www.youtube.com/watch?v=abc"],
                "cwd": str(tmp_path),
                "cookies": None,
                "aria2c": False,
                "format": "bv*+ba/b",
                "yt_dlp_version": "2025.01.01",
                "returncode": 1,
                "stderr_empty": True,
            }
        },
    )
    loaded = repo.get(job.id)
    text = format_full_error_report(loaded, app_version="0.5.4")
    assert text.strip()
    assert "0.5.4" in text
    assert "job_id: " in text and str(job.id) in text
    assert "https://www.youtube.com/watch?v=abc" in text
    assert "category:" in text
    assert "unknown" in text.lower() or "cause:" in text
    assert "yt_dlp" in text
    assert "returncode: 1" in text
    assert "no stderr" in text
    repo.close()


def test_fail_pause_and_auth_and_card_copy(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    job = ui.bridge.enqueue_url("https://www.youtube.com/watch?v=d")
    annotate_job_error(ui.repo, job.id, "Sign in to confirm you’re not a bot")
    payload = fail_pause_payload(ui.repo.get(job.id))
    ui.fail_pause_payload = payload
    dlg = ui._fail_pause_dialog(payload)
    labels = " ".join(str(getattr(a, "content", a)) for a in dlg.actions)
    assert "Copy full report" in labels
    text = ui._copy_fail_pause_report()
    assert ui.last_copied_report
    assert "bot" in text.lower()
    assert ui.page.clipboard == text

    auth = ui.open_authenticate("https://www.youtube.com/watch?v=d")
    auth_labels = " ".join(str(getattr(a, "content", a)) for a in auth.actions)
    assert "Copy error" in auth_labels
    ui._set_auth_error("Chrome import failed: profile locked")
    copied = ui._copy_auth_error()
    assert "Chrome import failed" in copied
    assert "https://www.youtube.com/watch?v=d" in copied

    card_text = ui.copy_job_error(job.id)
    assert str(job.id) in card_text
    assert card_text.strip()
    assert ui.page.clipboard == card_text
    assert ui.last_clipboard_status in {"sync", "scheduled", "set"}
    ui.shutdown()


def test_ffmpeg_fail_leads_with_retry_not_reauth(tmp_path: Path):
    from frameforge.errors import FFMPEG
    from frameforge.ui_flet.components.job_card import build_job_card
    from frameforge.ui_flet.job_view import fail_action_ids

    assert fail_action_ids(FFMPEG)[0] == "retry"
    assert "reauth" not in fail_action_ids(FFMPEG)
    repo = JobRepository(tmp_path / "f.db")
    job = repo.enqueue("https://example.com/v")
    annotate_job_error(repo, job.id, "ffmpeg failed: No such file or directory")
    card = build_job_card(repo.get(job.id), selected=False, expanded=True, show_progress=False)
    found = []

    def walk(ctrl):
        data = getattr(ctrl, "data", None)
        if isinstance(data, dict) and "fail_actions" in data:
            found.append(data)
        content = getattr(ctrl, "content", None)
        if content is not None:
            walk(content)
        for child in getattr(ctrl, "controls", None) or []:
            walk(child)

    walk(card)
    assert found
    assert found[0]["lead"] == "retry"
    assert found[0]["fail_actions"][0] == "retry"
    repo.close()
