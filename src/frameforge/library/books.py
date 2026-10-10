"""Books and folders for the local library.

Plex and Jellyfin keep movies and TV in separate libraries. People who filed
movies by genre lost that split when an app flattened everything into one
list, and Jellyfin has mistaken numbered movie folders for TV seasons.
FrameForge keeps the split as database links. The video file stays put.

A book is a top-level shelf (Movies, YouTube, Porn). A folder is a genre or
category inside that book.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KIND_BOOK = "book"

BOOKS: tuple[str, ...] = (
    "Movies",
    "TV Shows",
    "YouTube",
    "Facebook",
    "X",
    "TikTok",
    "Instagram",
    "Porn",
    "Other Videos",
)

MOVIE_FOLDERS: tuple[str, ...] = (
    "Action",
    "Comedy",
    "Drama",
    "Horror",
    "Science Fiction",
    "Documentary",
    "Animation",
    "Thriller",
    "Romance",
    "Other",
)

SOCIAL_FOLDERS: tuple[str, ...] = (
    "Comedy",
    "Informational",
    "Esoteric",
    "AI Fiction",
    "Music",
    "News",
    "Gaming",
    "Tutorial",
    "Other",
)

PORN_FOLDERS: tuple[str, ...] = ("Unsorted",)

CATALOG: dict[str, tuple[str, ...]] = {
    "Movies": MOVIE_FOLDERS,
    "TV Shows": MOVIE_FOLDERS,
    "YouTube": SOCIAL_FOLDERS,
    "Facebook": SOCIAL_FOLDERS,
    "X": SOCIAL_FOLDERS,
    "TikTok": SOCIAL_FOLDERS,
    "Instagram": SOCIAL_FOLDERS,
    "Porn": PORN_FOLDERS,
    "Other Videos": ("Clips", "Other"),
}

_TV_RE = re.compile(r"(?:s\d{1,2}e\d{1,2}|season\s*\d{1,2}|\b\d{1,2}x\d{2}\b)", re.I)
_YEAR_RE = re.compile(r"\((19|20)\d{2}\)")
_PORN_RE = re.compile(
    r"pornhub|eporner|xvideos|xnxx|xhamster|redtube|youporn|spankbang|porn",
    re.I,
)

_SOCIAL_BOOKS: tuple[tuple[str, str], ...] = (
    (r"youtube|youtu\.be", "YouTube"),
    (r"facebook|fb\.watch|fb\.com", "Facebook"),
    (r"(?:^|[\\/])x\.com|twitter", "X"),
    (r"tiktok", "TikTok"),
    (r"instagram", "Instagram"),
)

_SOCIAL_FOLDER_RULES: tuple[tuple[str, str], ...] = (
    (r"ai[\s\-]?fiction|aigc|ai[\s\-]?generated", "AI Fiction"),
    (r"esoteric|occult", "Esoteric"),
    (r"informational|explained|how[\s\-]?to|lecture", "Informational"),
    (r"tutorial", "Tutorial"),
    (r"comedy|stand[\s\-]?up|standup", "Comedy"),
    (r"\bnews\b", "News"),
    (r"gaming|\bgame\b", "Gaming"),
    (r"music|song", "Music"),
)

_GENRE_RULES: tuple[tuple[str, str], ...] = (
    (r"documentary", "Documentary"),
    (r"animation|cartoon|anime", "Animation"),
    (r"sci[\s\-]?fi|science fiction", "Science Fiction"),
    (r"horror", "Horror"),
    (r"thriller", "Thriller"),
    (r"romance", "Romance"),
    (r"comedy", "Comedy"),
    (r"action", "Action"),
    (r"drama", "Drama"),
)


def folder_kind(book: str) -> str:
    return f"book:{book}"


def ensure_books(store: Any) -> None:
    """Create every book and folder row. Does not create folders on disk."""
    from frameforge.db.repository import utc_now

    now = utc_now()
    for book, folders in CATALOG.items():
        store.conn.execute(
            """
            INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
            VALUES (?, ?, 1, NULL, ?)
            """,
            (book, KIND_BOOK, now),
        )
        for folder in folders:
            store.conn.execute(
                """
                INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
                VALUES (?, ?, 1, NULL, ?)
                """,
                (folder, folder_kind(book), now),
            )
    store.conn.commit()


def classify(
    path: str | Path,
    title: str | None = None,
    source: str | None = None,
    duration: float | None = None,
) -> tuple[str, str]:
    """Return ``(book, folder)`` from the path and title. Never looks at file bytes."""
    text = " ".join(
        part
        for part in (str(path), title or "", source or "")
        if part
    )
    lowered = text.lower()
    if _PORN_RE.search(lowered):
        return "Porn", _porn_folder(path)
    if _TV_RE.search(lowered):
        return "TV Shows", _match(_GENRE_RULES, lowered, "Other")
    social = _social_book(lowered)
    if social:
        return social, _match(_SOCIAL_FOLDER_RULES, lowered, "Other")
    long = duration is not None and float(duration) >= 70 * 60
    if long or _YEAR_RE.search(text) or re.search(r"[\\/]movies?[\\/]", lowered):
        return "Movies", _match(_GENRE_RULES, lowered, "Other")
    return "Other Videos", "Clips" if re.search(r"\bclip\b|shorts?", lowered) else "Other"


def _social_book(lowered: str) -> str | None:
    for pattern, book in _SOCIAL_BOOKS:
        if re.search(pattern, lowered):
            return book
    return None


def _match(rules: tuple[tuple[str, str], ...], lowered: str, default: str) -> str:
    for pattern, folder in rules:
        if re.search(pattern, lowered):
            return folder
    return default


def _porn_folder(path: str | Path) -> str:
    parent = Path(path).parent.name.strip()
    if (
        not parent
        or parent.lower() in {"porn", "uncategorized", "downloads"}
        or _PORN_RE.search(parent)
    ):
        return "Unsorted"
    words = re.sub(r"[^\w\s\-]+", " ", parent).split()
    if not words or len(words) > 3:
        return "Unsorted"
    label = " ".join(words[:3])
    return label[:40] if label.lower() != "unsorted" else "Unsorted"


def file_item(store: Any, item_id: int, *, path: str, title: str | None, source: str | None, duration: float | None) -> tuple[str, str]:
    """Put one library row in a book folder. The file path is not changed."""
    ensure_books(store)
    book, folder = classify(path, title, source, duration)
    kind = folder_kind(book)
    existing = store.get_collection_by_name(folder, kind)
    if existing is None:
        from frameforge.db.repository import utc_now

        store.conn.execute(
            """
            INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
            VALUES (?, ?, 1, NULL, ?)
            """,
            (folder, kind, utc_now()),
        )
        store.conn.commit()
        existing = store.get_collection_by_name(folder, kind)
    if existing is not None:
        store.set_primary_collection(item_id, existing.id)
    return book, folder


def already_filed(store: Any, item: Any) -> bool:
    cid = getattr(item, "primary_collection_id", None)
    if not cid:
        return False
    try:
        col = store.get_collection(int(cid))
    except KeyError:
        return False
    return str(col.kind).startswith("book:")


def sort_unfiled(store: Any) -> int:
    """File library rows that are not already in a book folder."""
    ensure_books(store)
    changed = 0
    for item in store.list_items(include_private=True):
        if already_filed(store, item):
            continue
        file_item(
            store,
            item.id,
            path=item.path,
            title=item.title,
            source=item.source,
            duration=item.duration,
        )
        changed += 1
    return changed
