"""Per-site folder keys derived from job URL / extractor."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Host / extractor aliases → folder name under the FrameForge root.
SITE_ALIASES: dict[str, str] = {
    "youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "youtu.be": "youtube",
    "music.youtube.com": "youtube",
    "youtube": "youtube",
    "twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
    "m.twitter.com": "x.com",
    "x.com": "x.com",
    "twitter": "x.com",
    "reddit.com": "reddit.com",
    "old.reddit.com": "reddit.com",
    "m.reddit.com": "reddit.com",
    "reddit": "reddit.com",
    "instagram.com": "instagram.com",
    "www.instagram.com": "instagram.com",
    "tiktok.com": "tiktok.com",
    "vm.tiktok.com": "tiktok.com",
    "vxtwitter.com": "x.com",
    "fxtwitter.com": "x.com",
}

_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_GENERIC_EXTRACTORS = frozenset({"", "generic", "unknown", "html5", "genericweb"})

# Do not let a site_key collide with global FrameForge subdirs.
_RESERVED = frozenset(
    {
        "downloads",
        "upscaled",
        "converted",
        "temp",
        "models",
        "archive",
        "cookies",
        "thumbnails",
        "frameforge.db",
    }
)


def sanitize_site_key(raw: str | None) -> str:
    """Windows-safe folder segment. Empty / illegal-only → other."""
    text = str(raw or "").strip().lower()
    text = _ILLEGAL_RE.sub("", text)
    text = text.strip(" .")
    if not text:
        return "other"
    if text in _RESERVED:
        return "other"
    return text[:64]


def _apply_alias(host_or_label: str) -> str:
    key = sanitize_site_key(host_or_label)
    if key == "other":
        return key
    if key in SITE_ALIASES:
        return SITE_ALIASES[key]
    return key


def site_key_from_url(url: str | None) -> str:
    """Folder key from a URL host (aliases + sanitize)."""
    text = str(url or "").strip()
    if not text:
        return "other"
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or " " in host or "\t" in host:
        return "other"
    return _apply_alias(host)


def site_key_from_extractor(extractor: str | None) -> str | None:
    """Map a yt-dlp extractor label, or None if it is too generic to trust."""
    label = str(extractor or "").strip().lower()
    if label in _GENERIC_EXTRACTORS:
        return None
    if label.startswith("www."):
        label = label[4:]
    mapped = _apply_alias(label)
    return mapped if mapped != "other" else None


def site_key_from_job(job: Any) -> str:
    """Prefer extractor, then URL host, then existing path parent, else other."""
    opts = job.options() if hasattr(job, "options") else {}
    cached = opts.get("site_key") if isinstance(opts, dict) else None
    if cached:
        return sanitize_site_key(str(cached))

    from_ext = site_key_from_extractor(getattr(job, "extractor", None))
    if from_ext:
        return from_ext

    from_url = site_key_from_url(getattr(job, "url", None))
    if from_url != "other":
        return from_url

    for raw in (getattr(job, "download_path", None), getattr(job, "output_path", None)):
        if not raw:
            continue
        parent = Path(str(raw)).parent.name
        key = _apply_alias(parent)
        if key != "other":
            return key
    return "other"
