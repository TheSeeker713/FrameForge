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
