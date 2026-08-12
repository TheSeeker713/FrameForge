"""Bulk TXT/MD URL importer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from frameforge.db.repository import JobRepository

URL_RE = re.compile(r"https?://[^\s<>\[\]()\"']+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", re.IGNORECASE)


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


def _clean_url(raw: str) -> str:
    url = raw.strip().rstrip(".,);]")
    # Strip trailing markdown punctuation
    while url and url[-1] in ".,);]>\"'":
        url = url[:-1]
    return url


def parse_lines(text: str) -> list[ImportItem]:
    items: list[ImportItem] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # HTML/markdown comment leftovers
        if line.startswith("<!--"):
            continue

        title: str | None = None
        url: str | None = None

        md = MD_LINK_RE.search(line)
        if md:
            title = md.group(1).strip() or None
            url = _clean_url(md.group(2))
        elif "|" in line:
            left, right = line.split("|", 1)
            left, right = left.strip(), right.strip()
            # Title | URL  or  URL | comment
            if right.lower().startswith("http"):
                title = left or None
                url = _clean_url(right.split()[0])
            elif left.lower().startswith("http"):
                url = _clean_url(left.split()[0])
            else:
                found = URL_RE.search(line)
                if found:
                    url = _clean_url(found.group(0))
        else:
            # URL with optional trailing comment
            found = URL_RE.search(line)
            if found:
                url = _clean_url(found.group(0))
                before = line[: found.start()].strip(" -:\t")
                after = line[found.end() :].strip()
                if before and not before.lower().startswith("http"):
                    title = before
                elif after.startswith("#"):
                    pass

        if not url or not url.lower().startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append(ImportItem(url=url, title=title))
    return items


def parse_file(path: str | Path) -> list[ImportItem]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return parse_lines(text)


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
    ids: list[int] = []
    for item in preview.items:
        if repo.url_in_queue(item.url) or repo.archive_lookup(item.url) is not None:
            continue
        job = repo.enqueue(
            item.url,
            title=item.title,
            priority=priority,
            format_preference=format_preference,
            upscale=upscale,
        )
        ids.append(job.id)
    return ids
