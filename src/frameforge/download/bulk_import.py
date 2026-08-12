"""Bulk TXT/MD URL importer.

Extracts http(s) video URLs from text and markdown lists, then previews
and enqueues them as **pending** (never auto-starts downloads).

Parser notes
------------
Previously: one URL per line via ``URL_RE.search``, markdown ``[text](url)``,
and ``Title | URL``. Lines starting with ``#`` were skipped entirely (so
``# https://youtube.com/watch?v=…`` yielded nothing). Files were read as
UTF-8 only, so UTF-16 Notepad “Unicode” lists decoded to NUL-padded text
and matched **zero** URLs.

Now: find **all** ``https?://`` matches per line (and markdown link groups),
strip trailing punctuation, keep unique order, decode UTF-8/UTF-16, and
still honor ``Title | URL`` plus ``[text](url)`` titles. Known hosts
without a scheme (youtube.com, youtu.be, x.com) get ``https://`` prepended.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from frameforge.db.repository import JobRepository

# Trailing ) ] are excluded so markdown ](url) and (url) wrappers do not swallow
# the closer. Query strings (?v= & si=) are included.
URL_RE = re.compile(r"https?://[^\s<>\"'\]\)]+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*(https?://[^)\s]+)\s*\)", re.IGNORECASE)
BARE_HOST_RE = re.compile(
    r"(?:^|[\s<(\[])("
    r"(?:www\.)?(?:youtube\.com|youtu\.be|x\.com|twitter\.com)"
    r"/[^\s<>\"'\]\)]+"
    r")",
    re.IGNORECASE,
)
_TRAIL_PUNCT = ".,;:)]>\"'"


@dataclass
class ImportItem:
    url: str
    title: str | None = None


@dataclass
class ImportPreview:
    items: list[ImportItem] = field(default_factory=list)
    skipped_dupe_count: int = 0
    skipped_invalid_count: int = 0

    @property
    def new_count(self) -> int:
        return len(self.items)


def _decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le", errors="ignore")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be", errors="ignore")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="ignore")
    sample = data[:200]
    if sample.count(b"\x00") >= max(4, len(sample) // 4):
        return data.decode("utf-16-le", errors="ignore")
    return data.decode("utf-8", errors="ignore").replace("\x00", "")


def _clean_url(raw: str) -> str:
    url = (raw or "").strip().replace("\x00", "").strip("<>")
    url = url.replace("&amp;", "&")
    while url and url[-1] in _TRAIL_PUNCT:
        url = url[:-1]
    return url.strip()


def _ensure_scheme(url: str) -> str | None:
    if not url:
        return None
    lowered = url.lower()
    if lowered.startswith(("http://", "https://")):
        return url
    if lowered.startswith(
        (
            "www.youtube.com/",
            "youtube.com/",
            "youtu.be/",
            "www.youtu.be/",
            "x.com/",
            "www.x.com/",
            "twitter.com/",
            "www.twitter.com/",
        )
    ):
        return "https://" + url
    return None


def parse_lines(text: str) -> list[ImportItem]:
    """Extract unique http(s) URLs in document order."""
    items: list[ImportItem] = []
    seen: set[str] = set()

    def add(raw: str, title: str | None = None) -> None:
        url = _ensure_scheme(_clean_url(raw))
        if not url or not url.lower().startswith(("http://", "https://")):
            return
        if url in seen:
            if title:
                for item in items:
                    if item.url == url and not item.title:
                        item.title = title
                        break
            return
        seen.add(url)
        items.append(ImportItem(url=url, title=title))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        pipe_title: str | None = None
        if "|" in line:
            left, right = line.split("|", 1)
            left, right = left.strip(), right.strip()
            if right.lower().startswith(("http://", "https://", "www.", "youtube.", "youtu.be")):
                if left and not left.lower().startswith("http"):
                    pipe_title = left

        for md in MD_LINK_RE.finditer(line):
            add(md.group(2), md.group(1).strip() or None)

        for found in URL_RE.finditer(line):
            before = line[: found.start()].strip(" \t-:*#")
            title = pipe_title
            if (
                title is None
                and before
                and not before.lower().startswith("http")
                and "://" not in before
                and "[" not in before
                and not before.startswith("|")
            ):
                title = before
            add(found.group(0), title)

        for found in BARE_HOST_RE.finditer(line):
            add(found.group(1), pipe_title)

    return items


def parse_file(path: str | Path) -> list[ImportItem]:
    data = Path(path).read_bytes()
    return parse_lines(_decode_bytes(data))


def preview_import(path: str | Path, repo: JobRepository) -> ImportPreview:
    parsed = parse_file(path)
    preview = ImportPreview()
    for item in parsed:
        if repo.url_in_queue(item.url) or repo.archive_lookup(item.url) is not None:
            preview.skipped_dupe_count += 1
            continue
        preview.items.append(item)
    return preview


def confirm_add(
    preview: ImportPreview,
    repo: JobRepository,
    *,
    priority: int = 0,
    format_preference: str = "best",
    upscale: bool = False,
) -> list[int]:
    from frameforge.download.metadata import site_label_from_url

    ids: list[int] = []
    for item in preview.items:
        if repo.url_in_queue(item.url) or repo.archive_lookup(item.url) is not None:
            continue
        # Bulk: inexpensive hostname label only (no per-URL network probe)
        job = repo.enqueue(
            item.url,
            title=item.title,
            extractor=site_label_from_url(item.url),
            priority=priority,
            format_preference=format_preference,
            upscale=upscale,
        )
        ids.append(job.id)
    return ids
