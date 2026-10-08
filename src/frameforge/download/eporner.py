"""Eporner page-hash selection and the yt-dlp plugin directory."""

from __future__ import annotations

import re
from pathlib import Path

# The page contains two 32-hex hashes. EP.user.hash is a session hash.
# player.hash is the one /xhr/video expects. Sending the user hash makes
# the API answer "Authorization failed. Try to reload page."
_PLAYER_HASH_RE = re.compile(
    r"""player\.hash\s*[:=]\s*["']([0-9a-fA-F]{32})""",
)
_ANY_HASH_RE = re.compile(
    r"""hash\s*[:=]\s*["']([0-9a-fA-F]{32})""",
)
_EPORNER_ID_RE = re.compile(
    r"eporner\.com/(?:(?:hd-porn|embed)/|video-)(?P<id>\w+)",
    re.IGNORECASE,
)


def plugin_root() -> str:
    """Directory whose child contains yt_dlp_plugins/extractor."""
    return str(Path(__file__).resolve().parent / "ytdlp_plugins")


def select_eporner_hash(webpage: str | None) -> str | None:
    """Prefer player.hash. Fall back to the first hash only if that is missing."""
    text = str(webpage or "")
    player = _PLAYER_HASH_RE.search(text)
    if player:
        return player.group(1)
    other = _ANY_HASH_RE.search(text)
    return other.group(1) if other else None


def eporner_embed_url(url: str | None) -> str | None:
    """Embed page for a watch URL. None when the URL is already an embed."""
    text = str(url or "").strip()
    match = _EPORNER_ID_RE.search(text)
    if not match:
        return None
    if re.search(r"eporner\.com/embed/", text, re.IGNORECASE):
        return None
    return f"https://www.eporner.com/embed/{match.group('id')}/"


def ensure_plugin_loaded() -> None:
    """Register the player-hash extractor for in-process YoutubeDL."""
    from yt_dlp.globals import all_plugins_loaded, plugin_dirs
    from yt_dlp.plugins import load_all_plugins

    root = plugin_root()
    current = list(plugin_dirs.value or ["default"])
    if root not in current:
        current.append(root)
        plugin_dirs.value = current
        all_plugins_loaded.value = False
    if not all_plugins_loaded.value:
        load_all_plugins()
