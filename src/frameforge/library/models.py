"""Library row types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LibraryItem:
    id: int
    job_id: int | None
    title: str | None
    source: str | None
    path: str
    width: int | None
    height: int | None
    duration: float | None
    thumb_path: str | None
    date_added: str
    date_modified: str | None
    is_private: bool
    is_favorite: bool
    watch_later: bool
    primary_collection_id: int | None
    source_url: str | None = None
    source_site: str | None = None
    primary_file_id: int | None = None
    duration_ms: int | None = None
    file_size: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> LibraryItem:
        keys = row.keys()
        return cls(
            id=int(row["id"]),
            job_id=int(row["job_id"]) if row["job_id"] is not None else None,
            title=row["title"],
            source=row["source"],
            path=row["path"],
            width=row["width"],
            height=row["height"],
            duration=row["duration"],
            thumb_path=row["thumb_path"],
            date_added=row["date_added"],
            date_modified=row["date_modified"],
            is_private=bool(row["is_private"]),
            is_favorite=bool(row["is_favorite"]) if "is_favorite" in keys else False,
            watch_later=bool(row["watch_later"]) if "watch_later" in keys else False,
            primary_collection_id=(
                int(row["primary_collection_id"])
                if row["primary_collection_id"] is not None
                else None
            ),
            source_url=row["source_url"] if "source_url" in keys else None,
            source_site=row["source_site"] if "source_site" in keys else None,
            primary_file_id=(
                int(row["primary_file_id"])
                if "primary_file_id" in keys and row["primary_file_id"] is not None
                else None
            ),
            duration_ms=(
                int(row["duration_ms"])
                if "duration_ms" in keys and row["duration_ms"] is not None
                else None
            ),
            file_size=(
                int(row["file_size"])
                if "file_size" in keys and row["file_size"] is not None
                else None
            ),
        )

    @property
    def resolution_label(self) -> str:
        if self.height is None:
            return "—"
        if self.width:
            return f"{self.width}×{self.height}"
        return f"{self.height}p"


@dataclass
class LibraryCollection:
    id: int
    name: str
    kind: str
    is_seeded: bool
    folder_name: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> LibraryCollection:
        return cls(
            id=int(row["id"]),
            name=row["name"],
            kind=row["kind"],
            is_seeded=bool(row["is_seeded"]),
            folder_name=row["folder_name"],
            created_at=row["created_at"],
        )

    @property
    def uses_folder(self) -> bool:
        return bool(self.folder_name) and self.kind in {"type", "custom"}


@dataclass
class LibraryFile:
    id: int
    item_id: int
    role: str
    path: str
    job_id: int | None
    scale: int | None
    model: str | None
    width: int | None
    height: int | None
    rotation: int | None
    duration_ms: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    pix_fmt: str | None
    size_bytes: int | None
    mtime_ns: int | None
    present: bool
    probed_at: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> LibraryFile:
        return cls(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            role=row["role"],
            path=row["path"],
            job_id=int(row["job_id"]) if row["job_id"] is not None else None,
            scale=int(row["scale"]) if row["scale"] is not None else None,
            model=row["model"],
            width=row["width"],
            height=row["height"],
            rotation=row["rotation"],
            duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
            fps=float(row["fps"]) if row["fps"] is not None else None,
            vcodec=row["vcodec"],
            acodec=row["acodec"],
            pix_fmt=row["pix_fmt"],
            size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
            mtime_ns=int(row["mtime_ns"]) if row["mtime_ns"] is not None else None,
            present=bool(row["present"]),
            probed_at=row["probed_at"],
            created_at=row["created_at"],
        )


@dataclass
class LibraryThumb:
    file_id: int
    cache_key: str
    thumb_path: str | None
    status: str
    error: str | None
    attempts: int
    last_used: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> LibraryThumb:
        return cls(
            file_id=int(row["file_id"]),
            cache_key=row["cache_key"],
            thumb_path=row["thumb_path"],
            status=row["status"],
            error=row["error"],
            attempts=int(row["attempts"] or 0),
            last_used=row["last_used"],
            created_at=row["created_at"],
        )
