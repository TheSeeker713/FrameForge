"""Locate yt-dlp / aria2c partial artifacts without deleting them."""

from __future__ import annotations

from pathlib import Path


def collect_partial_artifacts(
    output_dir: Path | str | None,
    extra_dirs: list[Path] | None = None,
) -> list[str]:
    """Return existing .part / .aria2 / .ytdl paths under *output_dir* (may be empty)."""
    found: list[str] = []
    roots: list[Path] = []
    if output_dir:
        roots.append(Path(output_dir))
    for extra in extra_dirs or []:
        roots.append(Path(extra))
    seen: set[str] = set()
    for folder in roots:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            name = path.name.lower()
            if name.endswith(".part") or name.endswith(".aria2") or name.endswith(".ytdl"):
                key = str(path.resolve()) if path.exists() else str(path)
                if key in seen:
                    continue
                seen.add(key)
                found.append(str(path))
    return sorted(found)
