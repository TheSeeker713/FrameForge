"""SQLite Library index (same DB as the download queue). Local only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from frameforge.db.repository import JobRepository, utc_now
from frameforge.library.models import LibraryCollection, LibraryItem
from frameforge.library.paths import safe_folder_name
from frameforge.library.taxonomy import (
    INGEST_FOLDER,
    INGEST_TYPE_NAME,
    KIND_CUSTOM,
    KIND_SOURCE,
    KIND_SUBJECT,
    KIND_TYPE,
    PRIVATE_FOLDER,
    RECENTLY_ADDED_DAYS,
    SOURCES,
    SUBJECTS,
    TYPES,
)

SETTING_ROOT = "library_root"
SETTING_ONBOARDED = "library_onboarded"
SORTS = ("date", "title", "resolution", "source")


class LibraryStore:
    def __init__(self, repo: JobRepository) -> None:
        self.repo = repo
        self.conn = repo.conn
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM library_collections").fetchone()
        if int(row["c"]) > 0:
            return
        now = utc_now()
        for name in SOURCES:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
                VALUES (?, ?, 1, NULL, ?)
                """,
                (name, KIND_SOURCE, now),
            )
        for name in TYPES:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (name, KIND_TYPE, name, now),
            )
        for name in SUBJECTS:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO library_collections(name, kind, is_seeded, folder_name, created_at)
                VALUES (?, ?, 1, NULL, ?)
                """,
                (name, KIND_SUBJECT, now),
            )
        self.conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self.repo.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.repo.set_setting(key, value)

    def root(self) -> Path | None:
        raw = self.get_setting(SETTING_ROOT)
        if not raw:
            return None
        return Path(raw)

    def set_root(self, path: str | Path) -> Path:
        from frameforge.layout import ensure_library_tree, resolve_library_home, repair_frameforge_tree

        root = resolve_library_home(path)
        ensure_library_tree(root)
        forge = root.parent
        if forge.name.lower() == "frameforge":
            repair_frameforge_tree(forge)
        self.set_setting(SETTING_ROOT, str(root))
        return root

    def is_onboarded(self) -> bool:
        return self.get_setting(SETTING_ONBOARDED, "0") == "1"

    def mark_onboarded(self) -> None:
        self.set_setting(SETTING_ONBOARDED, "1")

    def complete_onboarding(self, path: str | Path) -> Path:
        """Helper for tests: set root and mark finished. The GUI must not call this on folder pick."""
        root = self.set_root(path)
        self.mark_onboarded()
        return root

    def onboarding_step(self) -> str:
        """pick → move → done. Root without onboarded resumes at the transfer step."""
        if self.is_onboarded():
            return "done"
        if self.root() is not None:
            return "move"
        return "pick"

    def ingest_dir(self) -> Path:
        root = self.root()
        if root is None:
            raise RuntimeError("Library root is not set")
        dest = root / INGEST_FOLDER
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def private_dir(self) -> Path:
        root = self.root()
        if root is None:
            raise RuntimeError("Library root is not set")
        dest = root / PRIVATE_FOLDER
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def collection_folder(self, collection: LibraryCollection) -> Path | None:
        root = self.root()
        if root is None or not collection.uses_folder:
            return None
        dest = root / safe_folder_name(collection.folder_name or collection.name)
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def uncategorized(self) -> LibraryCollection:
        row = self.conn.execute(
            "SELECT * FROM library_collections WHERE name = ? AND kind = ?",
            (INGEST_TYPE_NAME, KIND_TYPE),
        ).fetchone()
        if row is None:
            self.ensure_defaults()
            row = self.conn.execute(
                "SELECT * FROM library_collections WHERE name = ? AND kind = ?",
                (INGEST_TYPE_NAME, KIND_TYPE),
            ).fetchone()
        return LibraryCollection.from_row(row)

    def get_collection(self, collection_id: int) -> LibraryCollection:
        row = self.conn.execute(
            "SELECT * FROM library_collections WHERE id = ?", (collection_id,)
        ).fetchone()
        if row is None:
            raise KeyError(collection_id)
        return LibraryCollection.from_row(row)

    def get_collection_by_name(self, name: str, kind: str | None = None) -> LibraryCollection | None:
        if kind:
            row = self.conn.execute(
                "SELECT * FROM library_collections WHERE name = ? AND kind = ?",
                (name, kind),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM library_collections WHERE name = ? ORDER BY id LIMIT 1",
                (name,),
            ).fetchone()
        return LibraryCollection.from_row(row) if row else None

    def list_collections(self, kind: str | None = None) -> list[LibraryCollection]:
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM library_collections WHERE kind = ? ORDER BY name COLLATE NOCASE",
                (kind,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM library_collections ORDER BY kind, name COLLATE NOCASE"
            ).fetchall()
        return [LibraryCollection.from_row(r) for r in rows]

    def create_collection(self, name: str, *, kind: str = KIND_CUSTOM) -> LibraryCollection:
        label = name.strip()
        if not label:
            raise ValueError("Collection name is required")
        folder = label if kind in {KIND_TYPE, KIND_CUSTOM} else None
        self.conn.execute(
            """
            INSERT INTO library_collections(name, kind, is_seeded, folder_name, created_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (label, kind, folder, utc_now()),
        )
        self.conn.commit()
        created = self.get_collection_by_name(label, kind)
        if created is None:
            raise RuntimeError("Failed to create collection")
        if created.uses_folder and self.root() is not None:
            self.collection_folder(created)
        return created

    def rename_collection(self, collection_id: int, name: str) -> LibraryCollection:
        col = self.get_collection(collection_id)
        label = name.strip()
        if not label:
            raise ValueError("Collection name is required")
        folder = label if col.uses_folder else col.folder_name
        self.conn.execute(
            "UPDATE library_collections SET name = ?, folder_name = ? WHERE id = ?",
            (label, folder, collection_id),
        )
        self.conn.commit()
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: int) -> None:
        col = self.get_collection(collection_id)
        if col.is_seeded and col.name == INGEST_TYPE_NAME:
            raise ValueError("Cannot delete Uncategorized")
        fallback = self.uncategorized()
        self.conn.execute(
            "UPDATE library_items SET primary_collection_id = ? WHERE primary_collection_id = ?",
            (fallback.id, collection_id),
        )
        self.conn.execute(
            "DELETE FROM library_item_collections WHERE collection_id = ?",
            (collection_id,),
        )
        self.conn.execute("DELETE FROM library_collections WHERE id = ?", (collection_id,))
        self.conn.commit()

    def get(self, item_id: int) -> LibraryItem:
        row = self.conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return LibraryItem.from_row(row)

    def get_by_job_id(self, job_id: int) -> LibraryItem | None:
        row = self.conn.execute(
            "SELECT * FROM library_items WHERE job_id = ?", (job_id,)
        ).fetchone()
        return LibraryItem.from_row(row) if row else None

    def get_by_path(self, path: str | Path) -> LibraryItem | None:
        target = str(Path(path))
        row = self.conn.execute(
            "SELECT * FROM library_items WHERE path = ?", (target,)
        ).fetchone()
        if row:
            return LibraryItem.from_row(row)
        resolved = str(Path(path).resolve()) if Path(path).exists() else target
        if resolved != target:
            row = self.conn.execute(
                "SELECT * FROM library_items WHERE path = ?", (resolved,)
            ).fetchone()
            if row:
                return LibraryItem.from_row(row)
        return None

    def add_item(
        self,
        *,
        path: str | Path,
        title: str | None = None,
        source: str | None = None,
        job_id: int | None = None,
        width: int | None = None,
        height: int | None = None,
        duration: float | None = None,
        thumb_path: str | None = None,
        primary_collection_id: int | None = None,
        is_private: bool = False,
    ) -> LibraryItem:
        now = utc_now()
        dest = str(Path(path).resolve()) if Path(path).exists() else str(Path(path))
        existing = self.get_by_path(dest)
        if existing:
            return existing
        if job_id is not None:
            by_job = self.get_by_job_id(job_id)
            if by_job:
                return by_job
        if primary_collection_id is None:
            primary_collection_id = self.uncategorized().id
        cur = self.conn.execute(
            """
            INSERT INTO library_items(
                job_id, title, source, path, width, height, duration, thumb_path,
                date_added, date_modified, is_private, is_favorite, watch_later,
                primary_collection_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                job_id,
                title,
                source,
                dest,
                width,
                height,
                duration,
                thumb_path,
                now,
                now,
                1 if is_private else 0,
                primary_collection_id,
            ),
        )
        item_id = int(cur.lastrowid)
        self.conn.execute(
            "INSERT OR IGNORE INTO library_item_collections(item_id, collection_id) VALUES (?, ?)",
            (item_id, primary_collection_id),
        )
        if source:
            src_col = self.get_collection_by_name(source, KIND_SOURCE)
            if src_col:
                self.conn.execute(
                    "INSERT OR IGNORE INTO library_item_collections(item_id, collection_id) VALUES (?, ?)",
                    (item_id, src_col.id),
                )
        self.conn.commit()
        return self.get(item_id)

    def update_item_path(self, item_id: int, path: str | Path) -> LibraryItem:
        dest = str(Path(path).resolve()) if Path(path).exists() else str(Path(path))
        self.conn.execute(
            "UPDATE library_items SET path = ?, date_modified = ? WHERE id = ?",
            (dest, utc_now(), item_id),
        )
        self.conn.commit()
        return self.get(item_id)

    def set_flags(
        self,
        item_id: int,
        *,
        is_favorite: bool | None = None,
        watch_later: bool | None = None,
        is_private: bool | None = None,
    ) -> LibraryItem:
        item = self.get(item_id)
        fav = item.is_favorite if is_favorite is None else is_favorite
        later = item.watch_later if watch_later is None else watch_later
        priv = item.is_private if is_private is None else is_private
        self.conn.execute(
            """
            UPDATE library_items
            SET is_favorite = ?, watch_later = ?, is_private = ?, date_modified = ?
            WHERE id = ?
            """,
            (1 if fav else 0, 1 if later else 0, 1 if priv else 0, utc_now(), item_id),
        )
        self.conn.commit()
        return self.get(item_id)

    def set_primary_collection(self, item_id: int, collection_id: int) -> LibraryItem:
        self.conn.execute(
            """
            UPDATE library_items SET primary_collection_id = ?, date_modified = ?
            WHERE id = ?
            """,
            (collection_id, utc_now(), item_id),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO library_item_collections(item_id, collection_id) VALUES (?, ?)",
            (item_id, collection_id),
        )
        self.conn.commit()
        return self.get(item_id)

    def add_tag(self, item_id: int, collection_id: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO library_item_collections(item_id, collection_id) VALUES (?, ?)",
            (item_id, collection_id),
        )
        self.conn.commit()

    def remove_tag(self, item_id: int, collection_id: int) -> None:
        item = self.get(item_id)
        if item.primary_collection_id == collection_id:
            fallback = self.uncategorized()
            self.set_primary_collection(item_id, fallback.id)
        self.conn.execute(
            "DELETE FROM library_item_collections WHERE item_id = ? AND collection_id = ?",
            (item_id, collection_id),
        )
        self.conn.commit()

    def item_collection_ids(self, item_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT collection_id FROM library_item_collections WHERE item_id = ?",
            (item_id,),
        ).fetchall()
        return [int(r["collection_id"]) for r in rows]

    def remove_item(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM library_item_collections WHERE item_id = ?", (item_id,))
        self.conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))
        self.conn.commit()

    def list_items(
        self,
        *,
        include_private: bool = False,
        search: str | None = None,
        source: str | None = None,
        collection_id: int | None = None,
        flag: str | None = None,
        sort: str = "date",
    ) -> list[LibraryItem]:
        sql = "SELECT * FROM library_items WHERE 1=1"
        params: list[Any] = []
        if not include_private:
            sql += " AND is_private = 0"
        needle = (search or "").strip()
        if needle:
            sql += " AND IFNULL(title,'') LIKE ?"
            params.append(f"%{needle}%")
        if source:
            sql += " AND source = ?"
            params.append(source)
        if collection_id is not None:
            sql += """
                AND id IN (
                    SELECT item_id FROM library_item_collections WHERE collection_id = ?
                )
            """
            params.append(collection_id)
        key = sort if sort in SORTS else "date"
        order = {
            "date": "date_added DESC, id DESC",
            "title": "IFNULL(title,'') COLLATE NOCASE ASC, id DESC",
            "resolution": "IFNULL(height,0) DESC, id DESC",
            "source": "IFNULL(source,'') COLLATE NOCASE ASC, id DESC",
        }[key]
        sql += f" ORDER BY {order}"
        rows = self.conn.execute(sql, params).fetchall()
        items = [LibraryItem.from_row(r) for r in rows]
        if flag:
            items = [i for i in items if self._matches_flag(i, flag)]
        return items

    def list_private_items(self) -> list[LibraryItem]:
        return [i for i in self.list_items(include_private=True) if i.is_private]

    def _matches_flag(self, item: LibraryItem, flag: str) -> bool:
        name = flag.strip().lower()
        if name in {"favorites", "favorite"}:
            return item.is_favorite
        if name in {"watch later", "watch_later"}:
            return item.watch_later
        if name in {"recently added", "recent"}:
            try:
                added = datetime.fromisoformat(item.date_added.replace("Z", "+00:00"))
                if added.tzinfo is None:
                    added = added.replace(tzinfo=timezone.utc)
                return datetime.now(timezone.utc) - added <= timedelta(days=RECENTLY_ADDED_DAYS)
            except ValueError:
                return False
        if "upscale candidate" in name or name in {"<=720p", "720p"}:
            return item.height is not None and 0 < item.height <= 720
        if name in {"1080p"}:
            return item.height is not None and 721 <= item.height < 2160
        if "4k" in name or "upscale blocked" in name:
            return item.height is not None and item.height >= 2160
        return True

    def list_watch_folders(self) -> list[tuple[int, Path, str]]:
        rows = self.conn.execute(
            "SELECT id, path, import_mode FROM library_watch_folders ORDER BY id"
        ).fetchall()
        return [(int(r["id"]), Path(r["path"]), str(r["import_mode"])) for r in rows]

    def add_watch_folder(self, path: str | Path, *, import_mode: str = "index") -> Path:
        dest = Path(path).expanduser().resolve()
        if not dest.is_dir():
            raise ValueError(f"Watch folder does not exist: {dest}")
        mode = import_mode if import_mode in {"index", "import"} else "index"
        self.conn.execute(
            """
            INSERT INTO library_watch_folders(path, import_mode) VALUES (?, ?)
            ON CONFLICT(path) DO UPDATE SET import_mode = excluded.import_mode
            """,
            (str(dest), mode),
        )
        self.conn.commit()
        return dest

    def remove_watch_folder(self, folder_id: int) -> None:
        self.conn.execute("DELETE FROM library_watch_folders WHERE id = ?", (folder_id,))
        self.conn.commit()
