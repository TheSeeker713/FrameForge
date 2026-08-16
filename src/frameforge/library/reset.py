"""Reset Library index and onboarding flags. Never deletes media by default."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.store import SETTING_ONBOARDED, SETTING_ROOT, LibraryStore


def reset_library_state(
    store: LibraryStore,
    *,
    clear_root: bool = True,
    revert_missing_job_paths: bool = True,
    download_roots: list[Path] | None = None,
) -> None:
    """Clear library_items, collections, watch folders, and onboarded.

    Media files on disk are left in place. Seeded collections are recreated.
    When *revert_missing_job_paths* is true, completed jobs whose download_path
    points at a missing Uncategorized/library file are pointed back at the same
    basename (or YouTube [id]) under *download_roots*.
    """
    old_root = store.root()
    if revert_missing_job_paths:
        from frameforge.library.ingest import heal_job_download_paths

        roots = [Path(p) for p in (download_roots or [])]
        if roots:
            heal_job_download_paths(store.repo, download_roots=roots, library_root=old_root)
    conn = store.conn
    conn.execute("DELETE FROM library_item_collections")
    conn.execute("DELETE FROM library_items")
    conn.execute("DELETE FROM library_watch_folders")
    conn.execute("DELETE FROM library_collections")
    conn.commit()
    store.set_setting(SETTING_ONBOARDED, "0")
    if clear_root:
        store.set_setting(SETTING_ROOT, "")
    store.ensure_defaults()
