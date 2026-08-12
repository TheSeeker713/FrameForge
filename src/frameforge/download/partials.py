"""Locate yt-dlp / aria2c partial artifacts without deleting them."""

from __future__ import annotations

from pathlib import Path


def collect_partial_artifacts(output_dir: Path | str | None) -> list[str]:
    """Return existing .part / .aria2 / .ytdl paths under *output_dir* (may be empty)."""
    if not output_dir:
        return []
    root = Path(output_dir)
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in root.iterdir():
        name = path.name.lower()
        if name.endswith(".part") or name.endswith(".aria2") or name.endswith(".ytdl"):
            found.append(str(path))
    return sorted(found)
