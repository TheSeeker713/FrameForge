"""Default Library taxonomy (local labels only — no cloud)."""

from __future__ import annotations

from typing import Any

from frameforge.paths_site import site_key_from_job

# Filters only — not folders.
SOURCES: tuple[str, ...] = (
    "YouTube",
    "TikTok",
    "X (Twitter)",
    "Reddit",
    "Facebook",
    "Instagram",
    "Vimeo",
    "Twitch",
    "Other",
)

# Default collections / labels — these get folders under the library root.
TYPES: tuple[str, ...] = (
    "Music Videos",
    "Tutorials",
    "Documentaries",
    "Shorts & Clips",
    "Movies",
    "Series",
    "Live & Streams",
    "Podcasts & Talk",
    "Uncategorized",
)

# Tags; multi-assign OK. Not folders unless the user makes one primary.
SUBJECTS: tuple[str, ...] = (
    "Comedy",
    "Horror",
    "Sci-Fi",
    "Action",
    "Drama",
    "Animation & Cartoons",
    "Gaming",
    "Tech",
    "Education",
    "News",
    "Sports",
    "Fitness",
    "Food & Cooking",
    "Travel",
    "DIY & Crafts",
    "ASMR",
    "Nature",
    "Art & Design",
    "Fashion",
    "Finance",
    "Other",
)

# Filter chips only — never user folders.
SYSTEM_FLAGS: tuple[str, ...] = (
    "Favorites",
    "Watch Later",
    "Recently Added",
    "Upscale candidate (≤720p)",
    "1080p",
    "4K+ (upscale blocked)",
)

KIND_SOURCE = "source"
KIND_TYPE = "type"
KIND_SUBJECT = "subject"
KIND_CUSTOM = "custom"

INGEST_TYPE_NAME = "Uncategorized"
INGEST_FOLDER = "Uncategorized"
PRIVATE_FOLDER = "Private"

SITE_KEY_TO_SOURCE: dict[str, str] = {
    "youtube": "YouTube",
    "tiktok.com": "TikTok",
    "tiktok": "TikTok",
    "x.com": "X (Twitter)",
    "twitter": "X (Twitter)",
    "reddit.com": "Reddit",
    "reddit": "Reddit",
    "facebook.com": "Facebook",
    "facebook": "Facebook",
    "fb.watch": "Facebook",
    "instagram.com": "Instagram",
    "instagram": "Instagram",
    "vimeo.com": "Vimeo",
    "vimeo": "Vimeo",
    "twitch.tv": "Twitch",
    "twitch": "Twitch",
}

RECENTLY_ADDED_DAYS = 7


def source_label_from_job(job: Any) -> str:
    """Map extractor/host to a seeded Source filter label."""
    key = site_key_from_job(job)
    if key in SITE_KEY_TO_SOURCE:
        return SITE_KEY_TO_SOURCE[key]
    lowered = (key or "").lower()
    for alias, label in SITE_KEY_TO_SOURCE.items():
        if lowered == alias or lowered.endswith("." + alias) or lowered.startswith(alias + "."):
            return label
    if "youtube" in lowered:
        return "YouTube"
    if "tiktok" in lowered:
        return "TikTok"
    if lowered in {"x.com", "twitter.com"} or "twitter" in lowered:
        return "X (Twitter)"
    return "Other"
