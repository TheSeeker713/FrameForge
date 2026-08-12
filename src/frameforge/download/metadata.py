"""Lightweight URL metadata (site/extractor + title) without downloading media."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from frameforge.download.ytdlp import YtDlpDownloader


def site_label_from_url(url: str) -> str:
    """Inexpensive hostname label used when extractor probe is unavailable."""
    host = (urlparse(url).hostname or urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


def probe_listing_metadata(
    url: str,
    *,
    cookiefile: Path | None = None,
) -> tuple[str | None, str]:
    title, extractor, _thumb = probe_listing_bundle(url, cookiefile=cookiefile)
    return title, extractor


def probe_listing_bundle(
    url: str,
    *,
    cookiefile: Path | None = None,
) -> tuple[str | None, str, str | None]:
    """Return (title, extractor_or_site, thumbnail_url) without downloading media."""
    fallback = site_label_from_url(url)
    try:
        from frameforge.download.cookies import resolve_cookiefile_for_url
        from frameforge.download.thumbnails import thumbnail_url_from_info

        cookie = cookiefile or resolve_cookiefile_for_url(url)
        dl = YtDlpDownloader(use_aria2c=False, cookiefile=cookie)
        info = dl.extract_info(url)
        title = info.get("title")
        extractor = (
            info.get("extractor_key")
            or info.get("extractor")
            or info.get("ie_key")
            or fallback
        )
        thumb = thumbnail_url_from_info(info)
        return (str(title) if title else None, str(extractor), thumb)
    except Exception:  # noqa: BLE001
        return (None, fallback, None)
