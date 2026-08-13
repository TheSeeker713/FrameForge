"""Phase A1 — v0.5 UI audit lists every command that must survive the Flet rewrite."""

from __future__ import annotations

from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "docs" / "AUDIT_UI_V05.md"

REQUIRED_IDS = (
    "add_url",
    "import_txt_md",
    "download_selected",
    "download_all_pending",
    "pause_selected",
    "resume_selected",
    "cancel_selected",
    "stop_after_current",
    "retry_failed",
    "upscale_selected",
    "convert_mp3",
    "select_recommended",
    "set_format",
    "clear_selected_queue",
    "clear_finished_queue",
    "open_folder",
    "reveal_file",
    "open_settings",
    "authenticate_site",
    "fail_pause_retry",
    "fail_pause_stop",
    "redownload_history",
    "playlist_enqueue_selected",
    "quit_cancel_and_quit",
    "quit_pause_and_quit",
    "quit_wait_then_quit",
    "tray_show",
    "tab_queue",
    "tab_history",
    "tab_thumbnails",
)


def _fenced_command_ids(text: str) -> set[str]:
    inside = False
    out: set[str] = set()
    for line in text.splitlines():
        if line.strip() == "```" and not inside:
            inside = True
            continue
        if line.strip() == "```" and inside:
            break
        if inside:
            token = line.strip()
            if token and not token.startswith("#"):
                out.add(token)
    return out


def test_audit_doc_lists_required_commands():
    text = AUDIT.read_text(encoding="utf-8")
    assert "python -m frameforge --gui" in text
    assert "create_app" in text
    ids = _fenced_command_ids(text)
    missing = [i for i in REQUIRED_IDS if i not in ids]
    assert not missing, f"AUDIT_UI_V05.md missing command ids: {missing}"
    assert "no auto-start" in text.lower() or "never arm" in text.lower()
    assert "single instance" in text.lower() or "single-instance" in text.lower()
