"""Flat playlist detection and entry listing (no media download)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

PLAYLIST_ENTRY_CAP = 500

ExtractFn = Callable[..., dict[str, Any]]


@dataclass
class PlaylistEntry:
    index: int
    url: str
    title: str | None = None
    video_id: str | None = None
    webpage_url: str | None = None


@dataclass
class PlaylistListing:
    url: str
    title: str | None
    playlist_id: str | None
    entries: list[PlaylistEntry] = field(default_factory=list)
    truncated: bool = False
    total_count: int | None = None


def looks_like_playlist_url(url: str) -> bool:
    """Cheap URL heuristic (not a substitute for extract)."""
    text = (url or "").lower()
    parsed = urlparse(url or "")
    qs = parse_qs(parsed.query)
    if "list" in qs or "playlist" in parsed.path.lower():
        return True
    if "/playlist" in text or "/sets/" in text or "/album/" in text:
        return True
    return False


def looks_like_playlist_info(info: dict[str, Any] | None) -> bool:
    if not isinstance(info, dict):
        return False
    kind = str(info.get("_type") or "").lower()
    if kind == "playlist":
        return True
    if kind in {"video", "url"}:
        return False
    entries = info.get("entries")
    return isinstance(entries, list) and len(entries) > 1


def _entry_watch_url(entry: dict[str, Any], page_url: str) -> str:
    webpage = entry.get("webpage_url") or entry.get("original_url")
    if isinstance(webpage, str) and webpage.startswith("http"):
        return webpage
    raw = entry.get("url")
    if isinstance(raw, str) and raw.startswith("http"):
        return raw
    vid = entry.get("id") or raw
    ie = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if vid and ("youtube" in ie or "youtu" in (page_url or "").lower()):
        return f"https://www.youtube.com/watch?v={vid}"
    return str(raw or vid or "")


def parse_flat_listing(
    page_url: str,
    info: dict[str, Any],
    *,
    cap: int = PLAYLIST_ENTRY_CAP,
) -> PlaylistListing | None:
    """Turn a yt-dlp info dict into a listing, or None for a single video."""
    if not looks_like_playlist_info(info):
        return None
    raw_entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
    total = info.get("playlist_count")
    if total is None:
        total = len(raw_entries)
    try:
        total_i = int(total)
    except (TypeError, ValueError):
        total_i = len(raw_entries)
    truncated = len(raw_entries) > cap or total_i > cap
    sliced = raw_entries[: max(0, cap)]
    entries: list[PlaylistEntry] = []
    for i, item in enumerate(sliced, start=1):
        idx = item.get("playlist_index") or item.get("playlist_autonumber") or i
        try:
            index = int(idx)
        except (TypeError, ValueError):
            index = i
        watch = _entry_watch_url(item, page_url)
        vid = item.get("id")
        title = item.get("title")
        entries.append(
            PlaylistEntry(
                index=index,
                url=watch,
                title=str(title) if title else None,
                video_id=str(vid) if vid else None,
                webpage_url=watch or None,
            )
        )
    return PlaylistListing(
        url=page_url,
        title=str(info.get("title")) if info.get("title") else None,
        playlist_id=str(info.get("id")) if info.get("id") else None,
        entries=entries,
        truncated=truncated,
        total_count=total_i,
    )


def ytdlp_flat_extract(
    url: str,
    *,
    cap: int = PLAYLIST_ENTRY_CAP,
    cookiefile: Path | None = None,
) -> dict[str, Any]:
    from yt_dlp import YoutubeDL

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
        "playlistend": int(cap),
    }
    if cookiefile and Path(cookiefile).is_file():
        opts["cookiefile"] = str(cookiefile)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise RuntimeError("flat extract returned non-dict")
    return info


def extract_playlist(
    url: str,
    *,
    cap: int = PLAYLIST_ENTRY_CAP,
    extract_fn: ExtractFn | None = None,
    cookiefile: Path | None = None,
) -> PlaylistListing | None:
    """Return a flat playlist listing, or None if *url* is a single video."""
    if extract_fn is not None:
        info = extract_fn(url)
    else:
        info = ytdlp_flat_extract(url, cap=cap, cookiefile=cookiefile)
    return parse_flat_listing(url, info, cap=cap)
