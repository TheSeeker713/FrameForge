"""Bulk document URL importer.

Extracts http(s) video URLs from text, markdown, RTF, and Word lists, then
previews and enqueues them as **pending** (never auto-starts downloads).

A heading in the document becomes the project category for the links under
it (at most two words). The host of each link chooses the bucket:
``downloads/<bucket>/<category>/``. Adult hosts use ``porn``; other hosts
use their site key (``youtube``, ``x.com``, ``bbc.com``, …).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

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
_LISTING_RE = re.compile(
    r"/(?:search|results|tag|tags|categories|category|feed|explore)(?:/|$|\?)",
    re.IGNORECASE,
)
_TRAIL_PUNCT = ".,;:)]>\"'"
_NUMBERED_TITLE_RE = re.compile(r"^\d+([.)])\s*$")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_LABEL_RE = re.compile(r"^(?:category|subject)\s*:\s*(.+)$", re.IGNORECASE)
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_GENERIC_PATH = frozenset(
    {
        "news",
        "watch",
        "video",
        "videos",
        "shorts",
        "embed",
        "status",
        "photo",
        "photos",
        "clip",
        "clips",
        "article",
        "articles",
        "story",
        "post",
        "posts",
        "view_video.php",
    }
)


@dataclass
class ImportItem:
    url: str
    title: str | None = None
    category: str | None = None
    note: str | None = None


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


def _unescape_docs(text: str) -> str:
    """Google Docs exports backslashes before punctuation (``https\\://``)."""
    return re.sub(r"\\(?=[^\s])", "", text)


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


def _is_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    target = parsed.path + ("?" if parsed.query else "")
    return _LISTING_RE.search(target) is not None


def _is_url_text(text: str) -> bool:
    raw = _unescape_docs(text).strip()
    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "www.")):
        return True
    return URL_RE.search(raw) is not None


def _clean_title(raw: str | None) -> str | None:
    if not raw:
        return None
    title = raw.strip()
    title = re.sub(r"^\d+[.)]\s+", "", title).strip()
    if not title or _NUMBERED_TITLE_RE.match(title) or _is_url_text(title):
        return None
    return title


def _is_id_segment(part: str) -> bool:
    if re.fullmatch(r"video-[A-Za-z0-9]+", part):
        return True
    if re.fullmatch(r"(?:ph)?[0-9a-f]{8,}", part, re.IGNORECASE):
        return True
    if re.fullmatch(r"[A-Za-z0-9]{11}", part):
        return True
    return False


def _subject_from_url(url: str) -> str | None:
    """Readable path slug. Watch ids and viewkeys are not subjects."""
    parts = [unquote(part) for part in urlparse(url).path.split("/") if part]
    humans: list[str] = []
    for part in parts:
        if _is_id_segment(part) or part.lower() in _GENERIC_PATH:
            continue
        slug = part
        for ext in (".html", ".htm", ".php", ".asp", ".aspx"):
            if slug.lower().endswith(ext):
                slug = slug[: -len(ext)]
        if not slug or _is_id_segment(slug):
            continue
        words = slug.replace("-", " ").replace("_", " ").replace("+", " ")
        words = re.sub(r"\s+", " ", words).strip()
        if not words or not re.search(r"[A-Za-z]", words):
            continue
        separated = "-" in part or "_" in part
        if not separated and len(words.split()) < 2 and len(part) < 8:
            continue
        humans.append(words)
    if not humans:
        return None
    return _clean_title(humans[-1])


def _strip_heading(line: str) -> str | None:
    """Full heading text, or None when the line is not a category label."""
    text = line.strip()
    if not text or _line_has_url(text):
        return None
    if re.fullmatch(r"[-*_]{2,}", text) or re.fullmatch(r"\d+[.)]?", text):
        return None
    md = _MD_HEADING_RE.match(text)
    if md:
        text = md.group(1).strip()
    elif text.startswith("#"):
        return None
    if len(text) >= 4 and text.startswith("**") and text.endswith("**"):
        text = text[2:-2].strip()
    elif len(text) >= 4 and text.startswith("__") and text.endswith("__"):
        text = text[2:-2].strip()
    labeled = _LABEL_RE.match(text)
    if labeled:
        text = labeled.group(1).strip()
    if not text or _line_has_url(text):
        return None
    return text


def _is_marked_heading(line: str) -> bool:
    text = line.strip()
    if _MD_HEADING_RE.match(text) or _LABEL_RE.match(text):
        return True
    if len(text) >= 4 and (
        (text.startswith("**") and text.endswith("**"))
        or (text.startswith("__") and text.endswith("__"))
    ):
        return True
    return False


def parse_lines(text: str) -> list[ImportItem]:
    """Extract unique http(s) URLs in document order, with category headings."""
    items: list[ImportItem] = []
    seen: set[str] = set()
    current_category: str | None = None
    current_note: str | None = None
    section_has_url = False

    def add(raw: str, title: str | None = None) -> None:
        nonlocal section_has_url
        url = _ensure_scheme(_clean_url(raw))
        if not url or not url.lower().startswith(("http://", "https://")):
            return
        if _is_listing_url(url):
            return
        usable = _clean_title(title)
        if usable is None:
            usable = _subject_from_url(url)
        if url in seen:
            if usable:
                for item in items:
                    if item.url == url and not item.title:
                        item.title = usable
                        break
            return
        seen.add(url)
        section_has_url = True
        items.append(
            ImportItem(url=url, title=usable, category=current_category, note=current_note)
        )

    for raw_line in _unescape_docs(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+[.)]?", line) or re.fullmatch(r"[-*_]{2,}", line):
            continue

        if not _line_has_url(line):
            heading = _strip_heading(line)
            if heading is None:
                continue
            from frameforge.paths_site import sanitize_category

            start_section = (
                _is_marked_heading(line) or current_category is None or section_has_url
            )
            if start_section:
                current_category = sanitize_category(heading)
                current_note = heading
                section_has_url = False
            elif current_note:
                current_note = current_note + "\n" + heading
            else:
                current_note = heading
            continue

        pipe_title: str | None = None
        if "|" in line:
            left, right = line.split("|", 1)
            left, right = left.strip(), right.strip()
            if right.lower().startswith(("http://", "https://", "www.", "youtube.", "youtu.be")):
                pipe_title = _clean_title(left)

        for md in MD_LINK_RE.finditer(line):
            add(md.group(2), _clean_title(md.group(1)))

        for found in URL_RE.finditer(line):
            before = line[: found.start()].strip(" \t-:*#")
            before = re.sub(r"^\d+[.)]\s*", "", before).strip()
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


def _rtf_to_text(data: bytes) -> str:
    text = _decode_bytes(data)
    text = re.sub(r"\\par[d]?\b ?", "\n", text)
    text = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda match: bytes.fromhex(match.group(1)).decode("latin-1", "ignore"),
        text,
    )
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    return text.replace("{", "").replace("}", "")


def _docx_to_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_W_NS}p"):
        chunks = [node.text or "" for node in paragraph.iter(f"{_W_NS}t")]
        paragraphs.append("".join(chunks))
    return "\n".join(paragraphs)


def _doc_to_text(data: bytes) -> str:
    """Pull readable UTF-16 text runs out of a legacy Word binary."""
    runs: list[str] = []
    chars: list[str] = []
    i = 0
    while i + 1 < len(data):
        lo = data[i]
        hi = data[i + 1]
        if hi == 0 and (lo in (9, 10, 13) or 32 <= lo < 127):
            chars.append("\n" if lo in (10, 13) else chr(lo))
            i += 2
            continue
        if len(chars) >= 6:
            runs.append("".join(chars))
        chars = []
        i += 1
    if len(chars) >= 6:
        runs.append("".join(chars))
    return "\n".join(runs)


def text_from_bytes(data: bytes, suffix: str) -> str:
    kind = suffix.lower()
    if kind == ".docx":
        return _docx_to_text(data)
    if kind == ".doc":
        return _doc_to_text(data)
    if kind == ".rtf":
        return _rtf_to_text(data)
    return _decode_bytes(data)


def parse_file(path: str | Path) -> list[ImportItem]:
    file_path = Path(path)
    return parse_lines(text_from_bytes(file_path.read_bytes(), file_path.suffix))


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
        options: dict[str, str] = {
            "download_output_dir": str(out_dir),
            "download_category": category,
            "site_key": site_key,
        }
        if item.note:
            options["import_note"] = item.note
        # Bulk: inexpensive hostname label only (no per-URL network probe)
        job = repo.enqueue(
            item.url,
            title=item.title,
            extractor=site_label_from_url(item.url),
            priority=priority,
            format_preference=format_preference,
            upscale=upscale,
            options=options,
        )
        ids.append(job.id)
    return ids
