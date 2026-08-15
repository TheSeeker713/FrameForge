"""B1 — classify yt-dlp stderr corpora without network."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.errors import (
    BOT_CHECK,
    UNKNOWN,
    annotate_job_error,
    classify_error,
    format_ytdlp_exit_error,
    human_cause,
)
from tests.fixtures.stderr_corpus import CORPUS


def test_stderr_corpus_maps_to_category_with_cause_and_tail(tmp_path: Path):
    repo = JobRepository(tmp_path / "corpus.db")
    for i, (expected, blob) in enumerate(CORPUS):
        wrapped = format_ytdlp_exit_error(1, blob.splitlines())
        assert classify_error(wrapped) == expected, blob
        if expected != UNKNOWN:
            assert "yt-dlp exited with code 1" in wrapped
            assert wrapped.strip() != "yt-dlp exited with code 1"
        job = repo.enqueue(f"https://example.com/{i}")
        annotate_job_error(repo, job.id, wrapped)
        loaded = repo.get(job.id)
        opts = loaded.options()
        assert opts.get("error_category") == expected
        cause = opts.get("error_cause") or ""
        assert cause.strip(), blob
        assert cause == human_cause(expected)
        tail = opts.get("error_stderr_tail") or ""
        if expected != UNKNOWN:
            assert tail.strip(), blob
    repo.close()


def test_bare_exit_code_without_stderr_is_unknown():
    msg = format_ytdlp_exit_error(1, [])
    assert "yt-dlp exited with code 1" in msg
    assert "no stderr; see invocation log" in msg
    assert classify_error(msg) == UNKNOWN


def test_bot_line_inside_exit_wrapper_is_bot_check():
    msg = format_ytdlp_exit_error(
        1,
        ["[debug] Encodings: utf-8", "ERROR: [youtube] x: Sign in to confirm you’re not a bot"],
    )
    assert classify_error(msg) == BOT_CHECK
    assert "not a bot" in msg
