"""Step 2.1 — per-job format preference persists independently of the global default."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.formats import FORMAT_PRESETS, resolve_format_selector


def test_format_override_persists_across_reopen(tmp_path: Path):
    db = tmp_path / "f.db"
    repo = JobRepository(db)
    repo.set_setting("format_preference", "best")
    a = repo.enqueue("https://example.com/a", format_preference="best")
    b = repo.enqueue("https://example.com/b", format_preference=FORMAT_PRESETS["≤720p"])
    repo.set_format_preference(a.id, FORMAT_PRESETS["≤1080p"])
    aid, bid = a.id, b.id
    repo.close()

    repo2 = JobRepository(db)
    assert repo2.get_setting("format_preference") == "best"
    assert repo2.get(aid).format_preference == FORMAT_PRESETS["≤1080p"]
    assert repo2.get(bid).format_preference == FORMAT_PRESETS["≤720p"]
    assert resolve_format_selector(repo2.get(aid).format_preference) != resolve_format_selector(
        "best"
    )
    repo2.close()
