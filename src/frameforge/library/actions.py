"""Play / reveal / upscale eligibility for Library items."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.models import LibraryItem
from frameforge.upscale.guards import MIN_BLOCK_HEIGHT, is_upscale_blocked
from frameforge.util.reveal import RevealError, open_in_default_player, reveal_file


def can_upscale_library_item(item: LibraryItem) -> bool:
    if is_upscale_blocked(item.height):
        return False
    return Path(item.path).is_file()


def upscale_blocked_reason(item: LibraryItem) -> str | None:
    if item.height is not None and item.height >= MIN_BLOCK_HEIGHT:
        return f"Upscale blocked: source is 4K/≥2160p (height={item.height})"
    if not Path(item.path).is_file():
        return "File not found — cannot upscale"
    return None


def play_library_item(item: LibraryItem, *, launch: bool = True) -> Path:
    path = Path(item.path)
    if not path.is_file():
        raise RevealError(f"Path does not exist: {path}")
    return open_in_default_player(path, launch=launch)


def reveal_library_item(item: LibraryItem, *, launch: bool = True) -> Path:
    path = Path(item.path)
    if not path.is_file():
        raise RevealError(f"Path does not exist: {path}")
    return reveal_file(path, launch=launch)
