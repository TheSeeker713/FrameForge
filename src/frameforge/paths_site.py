"""Per-site download buckets and category folder keys."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Host / extractor aliases → streaming site folder under downloads/.
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
    "pornhub.com": "pornhub.com",
    "www.pornhub.com": "pornhub.com",
    "pornhub": "pornhub.com",
    "pornhubpremium.com": "pornhub.com",
    "xvideos.com": "xvideos.com",
    "www.xvideos.com": "xvideos.com",
    "xnxx.com": "xnxx.com",
    "www.xnxx.com": "xnxx.com",
    "xhamster.com": "xhamster.com",
    "www.xhamster.com": "xhamster.com",
}

# Adult hosts land under downloads/porn/{category}, not downloads/pornhub.com/.
PORN_SITE_KEYS: frozenset[str] = frozenset(
    {
        "pornhub.com",
        "pornhubpremium.com",
        "xvideos.com",
        "xnxx.com",
        "xhamster.com",
        "redtube.com",
        "youporn.com",
        "tube8.com",
        "spankbang.com",
        "chaturbate.com",
        "onlyfans.com",
    }
)

DEFAULT_CATEGORY = "uncategorized"
PORN_BUCKET = "porn"

_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_GENERIC_EXTRACTORS = frozenset({"", "generic", "unknown", "html5", "genericweb"})

# Do not let a site_key collide with global FrameForge / downloads subdirs.
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
        "database",
        "videos",
        "metadata",
        "library",
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


def sanitize_category(raw: str | None) -> str:
    """Windows-safe project category folder under a download bucket."""
    text = str(raw or "").strip()
    text = _ILLEGAL_RE.sub("", text)
    text = text.strip(" .")
    # Strip a trailing sentence period often used in list headings.
    if text.endswith("."):
        text = text[:-1].rstrip(" .")
    text = re.sub(r"\s+", " ", text)
    if not text:
        return DEFAULT_CATEGORY
    lowered = text.lower()
    if lowered in _RESERVED or lowered == DEFAULT_CATEGORY:
        return DEFAULT_CATEGORY if lowered == DEFAULT_CATEGORY else sanitize_site_key(text)
    return text[:80]


def _apply_alias(host_or_label: str) -> str:
    key = sanitize_site_key(host_or_label)
    if key == "other":
        return key
    if key in SITE_ALIASES:
        return SITE_ALIASES[key]
    return key


def download_bucket_for_site_key(site_key: str | None) -> str:
    """Top-level folder under downloads/: porn, youtube, x.com, …"""
    raw = str(site_key or "").strip().lower()
    if raw == PORN_BUCKET:
        return PORN_BUCKET
    key = sanitize_site_key(site_key)
    if key in PORN_SITE_KEYS:
        return PORN_BUCKET
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
        key = sanitize_site_key(str(cached))
        if key != PORN_BUCKET:
            return key

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
        if key != "other" and key != PORN_BUCKET and key != DEFAULT_CATEGORY:
            return key
    return "other"


def category_from_job(job: Any) -> str:
    opts = job.options() if hasattr(job, "options") else {}
    if not isinstance(opts, dict):
        return DEFAULT_CATEGORY
    for key in ("download_category", "project_category", "category"):
        raw = opts.get(key)
        if raw:
            return sanitize_category(str(raw))
    return DEFAULT_CATEGORY
