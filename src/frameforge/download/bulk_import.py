"""Bulk TXT/MD URL importer.

Extracts http(s) video URLs from text and markdown lists, then previews
and enqueues them as **pending** (never auto-starts downloads).

Heading lines without a URL become the project category for following
links (``downloads/<bucket>/<category>/``). Adult hosts use the ``porn``
bucket; streaming sites use their site key (``youtube``, ``x.com``, …).
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
_NUMBERED_TITLE_RE = re.compile(r"^\d+([.)])\s*$")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


@dataclass
class ImportItem:
    url: str
    title: str | None = None
    category: str | None = None


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


def _line_has_url(line: str) -> bool:
    if URL_RE.search(line) or MD_LINK_RE.search(line) or BARE_HOST_RE.search(line):
        return True
    return False


def _heading_category(line: str) -> str | None:
    """Return a project category from a heading line that has no URL."""
    text = line.strip()
    if not text or _line_has_url(text):
        return None
    md = _MD_HEADING_RE.match(text)
    if md:
        text = md.group(1).strip()
    elif text.startswith("#"):
        # Comment-only line without a URL — not a category.
        return None
    # Skip bare list markers / separators.
    if re.fullmatch(r"[-*_]{2,}", text):
        return None
    if re.fullmatch(r"\d+([.)])?", text):
        return None
    from frameforge.paths_site import sanitize_category

    return sanitize_category(text)


def _clean_title(raw: str | None) -> str | None:
    if not raw:
        return None
    title = raw.strip()
    if not title or _NUMBERED_TITLE_RE.match(title):
        return None
    return title


def parse_lines(text: str) -> list[ImportItem]:
    """Extract unique http(s) URLs in document order, with category headings."""
    items: list[ImportItem] = []
    seen: set[str] = set()
    current_category: str | None = None

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
        items.append(ImportItem(url=url, title=title, category=current_category))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = _heading_category(line)
        if heading is not None:
            current_category = heading
            continue

        pipe_title: str | None = None
        if "|" in line:
            left, right = line.split("|", 1)
            left, right = left.strip(), right.strip()
            if right.lower().startswith(("http://", "https://", "www.", "youtube.", "youtu.be")):
                if left and not left.lower().startswith("http"):
                    pipe_title = _clean_title(left)

        for md in MD_LINK_RE.finditer(line):
            add(md.group(2), _clean_title(md.group(1)))

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
                title = _clean_title(before)
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
    from frameforge.paths import download_dir_for_site
    from frameforge.paths_site import DEFAULT_CATEGORY, sanitize_category, site_key_from_url

    ids: list[int] = []
    for item in preview.items:
        if repo.url_in_queue(item.url) or repo.archive_lookup(item.url) is not None:
            continue
        site_key = site_key_from_url(item.url)
        category = sanitize_category(item.category) if item.category else DEFAULT_CATEGORY
        out_dir = download_dir_for_site(site_key, category)
        # Bulk: inexpensive hostname label only (no per-URL network probe)
        job = repo.enqueue(
            item.url,
            title=item.title,
            extractor=site_label_from_url(item.url),
            priority=priority,
            format_preference=format_preference,
            upscale=upscale,
            options={
                "download_output_dir": str(out_dir),
                "download_category": category,
                "site_key": site_key,
            },
        )
        ids.append(job.id)
    return ids
