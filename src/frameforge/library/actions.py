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


def _existing_media(item: LibraryItem) -> Path:
    path = Path(item.path)
    if path.is_file():
        return path
    raise RevealError(f"Path does not exist: {path}")


def open_library_item_externally(item: LibraryItem, *, launch: bool = True) -> Path:
    """Open the file in the operating system's player.

    The in-app player is ``FrameForgeUi.play_library_item``. This function is the
    external one.
    """
    return open_in_default_player(_existing_media(item), launch=launch)


def play_library_item(item: LibraryItem, *, launch: bool = True) -> Path:
    """Old name for :func:`open_library_item_externally`."""
    return open_library_item_externally(item, launch=launch)


def reveal_library_item(item: LibraryItem, *, launch: bool = True) -> Path:
    return reveal_file(_existing_media(item), launch=launch)
