"""Per-job yt-dlp format presets (global default remains 'best')."""

from __future__ import annotations

FORMAT_PRESETS: dict[str, str] = {
    "Best": "best",
    "≤1080p": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
    "≤720p": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
    "≤480p": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
    "Audio-focused": "ba/b",
}

PRESET_LABELS = tuple(FORMAT_PRESETS.keys())


def resolve_format_selector(preference: str | None) -> str:
    """Map stored preference to a yt-dlp -f string."""
    text = (preference or "best").strip() or "best"
    if text in FORMAT_PRESETS:
        text = FORMAT_PRESETS[text]
    if text == "best":
        return "bv*+ba/b"
    return text


def label_for_preference(preference: str | None) -> str:
    text = (preference or "best").strip() or "best"
    for label, value in FORMAT_PRESETS.items():
        if text == value or text == label:
            return label
    if text == "best":
        return "Best"
    return text
