"""Step 2.3 — download opts honor per-job format preference."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.formats import FORMAT_PRESETS, resolve_format_selector
from frameforge.download.ytdlp import YtDlpDownloader


def test_two_jobs_produce_different_format_opts(tmp_path: Path):
    repo = JobRepository(tmp_path / "fmt.db")
    best = repo.enqueue("https://example.com/best", format_preference="best")
    capped = repo.enqueue(
        "https://example.com/720",
        format_preference=FORMAT_PRESETS["≤720p"],
    )
    audio = repo.enqueue(
        "https://example.com/audio",
        format_preference="Audio-focused",
    )

    dl = YtDlpDownloader(output_dir=tmp_path / "dl")
    seen: dict[int, str] = {}
    for job in (best, capped, audio):
        dl.format_preference = job.format_preference or "best"
        fmt = dl.build_opts()["format"]
        seen[job.id] = fmt
        cmd = dl._build_cli_cmd(job.url)
        assert "-f" in cmd
        assert cmd[cmd.index("-f") + 1] == fmt

    assert seen[best.id] == resolve_format_selector("best")
    assert seen[capped.id] == resolve_format_selector("≤720p")
    assert seen[audio.id] == resolve_format_selector("Audio-focused")
    assert seen[best.id] != seen[capped.id]
    assert seen[capped.id] != seen[audio.id]
    assert "720" in seen[capped.id]
    assert seen[audio.id].startswith("ba")
    repo.close()
