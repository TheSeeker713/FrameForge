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
    "facebook.com": "facebook",
    "m.facebook.com": "facebook",
    "mbasic.facebook.com": "facebook",
    "fb.watch": "facebook",
    "fb.com": "facebook",
    "facebook": "facebook",
    "facebookredirect": "facebook",
    "facebookpluginsvideo": "facebook",
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
        "eporner.com",
        "eporner",
        "pornhub.org",
    }
)

# Streaming hosts live under downloads/social/<platform>/<category>/.
SOCIAL_PLATFORM_KEYS: frozenset[str] = frozenset({"youtube", "x.com", "facebook"})

DEFAULT_CATEGORY = "uncategorized"
PORN_BUCKET = "porn"
_EXPLICIT_TITLE = re.compile(
    r"\b(sex|porn|xxx|anal|orgy|fivesome|threesome|blowjob|cumshot|milf|nude|naked|nsfw|anilingus|erotic)\b",
    re.IGNORECASE,
)
_GENERIC_META = frozenset(
    {"", "uncategorized", "other", "video", "videos", "default", "none", "general", "adult"}
)
_FACEBOOK_ID = re.compile(r"\[(\d{12,})\]")

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
        "social",
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
    """Windows-safe category folder: at most the first two words.

    A second sentence is dropped before the word cut. Commas and ellipses
    are not words. One word stays one word.
    """
    text = str(raw or "").strip()
    text = _ILLEGAL_RE.sub("", text)
    text = text.replace("…", ".")
    text = re.sub(r"\s+", " ", text).strip(" .")
    sentence = re.split(r"[.!?]", text, maxsplit=1)[0]
    words: list[str] = []
    for raw_word in sentence.split():
        token = raw_word.strip(".,;:!?\"'`“”()[]{}")
        token = token.strip("-–—")
        if token:
            words.append(token)
        if len(words) >= 2:
            break
    text = " ".join(words)
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


def is_porn_site_key(site_key: str | None) -> bool:
    """True for adult hosts, including eporner.com and subdomains."""
    raw = str(site_key or "").strip().lower()
    if raw == PORN_BUCKET:
        return True
    key = sanitize_site_key(site_key)
    aliased = _apply_alias(key)
    if key in PORN_SITE_KEYS or aliased in PORN_SITE_KEYS:
        return True
    return any(
        key == host or key.endswith("." + host) or aliased == host or aliased.endswith("." + host)
        for host in PORN_SITE_KEYS
    )


def is_social_platform(site_key: str | None) -> bool:
    key = _apply_alias(sanitize_site_key(site_key))
    return key in SOCIAL_PLATFORM_KEYS


def download_bucket_for_site_key(site_key: str | None) -> str:
    """Leaf bucket: ``porn``, ``youtube``, ``x.com``, ``facebook``, or the host.

    Social platforms are still these leaf names. ``download_dir_for_site``
    nests them under ``downloads/social/``.
    """
    raw = str(site_key or "").strip().lower()
    if raw == PORN_BUCKET:
        return PORN_BUCKET
    key = _apply_alias(sanitize_site_key(site_key))
    if key in SOCIAL_PLATFORM_KEYS:
        return key
    if is_porn_site_key(key):
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
    """Prefer a social URL, then extractor, then URL host, else other.

    A saved ``site_key`` must not keep a Facebook link inside an adult folder.
    """
    from_url = site_key_from_url(getattr(job, "url", None))
    from_ext = site_key_from_extractor(getattr(job, "extractor", None))
    if is_social_platform(from_url):
        return download_bucket_for_site_key(from_url)
    if is_social_platform(from_ext) and from_url == "other":
        return download_bucket_for_site_key(from_ext)

    opts = job.options() if hasattr(job, "options") else {}
    cached = opts.get("site_key") if isinstance(opts, dict) else None
    if cached:
        key = sanitize_site_key(str(cached))
        stale_adult = is_porn_site_key(key) and from_url != "other" and not is_porn_site_key(from_url)
        if key != PORN_BUCKET and not stale_adult:
            return key

    if from_ext:
        return from_ext

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
    locked = user_category(job)
    return locked if locked else DEFAULT_CATEGORY


def user_category(job: Any) -> str | None:
    """Import heading or other chosen category. ``uncategorized`` is not a choice."""
    opts = job.options() if hasattr(job, "options") else {}
    if not isinstance(opts, dict):
        return None
    for key in ("download_category", "project_category", "category"):
        raw = opts.get(key)
        if not raw:
            continue
        chosen = sanitize_category(str(raw))
        if chosen != DEFAULT_CATEGORY:
            return chosen
    return None


def facebook_id_in_name(name: str | None) -> bool:
    """Facebook video ids are long digit strings. Eporner ids are not."""
    return _FACEBOOK_ID.search(str(name or "")) is not None


def title_from_media_name(name: str | None) -> str:
    stem = Path(str(name or "")).stem
    stem = re.sub(r"\s*\[[^\]]*\]\s*", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _meta_label(raw: object) -> str | None:
    text = _ILLEGAL_RE.sub("", str(raw or "")).strip(" .")
    if not text or text.lower() in _GENERIC_META:
        return None
    if _EXPLICIT_TITLE.search(text):
        return None
    if len(text) <= 40 and len(text.split()) <= 4:
        return text
    chosen = sanitize_category(text)
    if chosen == DEFAULT_CATEGORY or _EXPLICIT_TITLE.search(chosen):
        return None
    return chosen


def category_from_metadata(
    info: dict[str, Any] | None,
    *,
    title: str | None = None,
    user_category_name: str | None = None,
) -> str:
    """Category from an import heading, then page metadata, then a plain title.

    An explicit sexual title is not turned into a folder name. Adult files
    still stay in the porn bucket; this only chooses the category under it.
    """
    if user_category_name:
        chosen = sanitize_category(user_category_name)
        if chosen != DEFAULT_CATEGORY:
            return chosen
    data = info or {}
    for key in ("playlist_title", "album", "series"):
        label = _meta_label(data.get(key))
        if label:
            return label
    categories = data.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]
    if isinstance(categories, (list, tuple)):
        for raw in categories:
            label = _meta_label(raw)
            if label:
                return label
    for key in ("genre", "album"):
        label = _meta_label(data.get(key))
        if label:
            return label
    title_text = str(title or data.get("title") or "")
    if title_text and not _EXPLICIT_TITLE.search(title_text):
        chosen = sanitize_category(title_text)
        if chosen != DEFAULT_CATEGORY:
            return chosen
    return DEFAULT_CATEGORY


def site_key_from_info(info: dict[str, Any] | None) -> str | None:
    """Host or extractor from a finished yt-dlp info dict."""
    if not isinstance(info, dict):
        return None
    for key in ("webpage_url", "original_url", "url"):
        host_key = site_key_from_url(str(info.get(key) or ""))
        if is_social_platform(host_key) or is_porn_site_key(host_key):
            return download_bucket_for_site_key(host_key)
    extracted = site_key_from_extractor(str(info.get("extractor_key") or info.get("extractor") or ""))
    if extracted and (is_social_platform(extracted) or is_porn_site_key(extracted)):
        return download_bucket_for_site_key(extracted)
    video_id = str(info.get("id") or "")
    if video_id.isdigit() and len(video_id) >= 12:
        return "facebook"
    return None
