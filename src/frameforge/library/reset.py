"""Reset Library index and onboarding flags. Never deletes media by default."""

from __future__ import annotations

from frameforge.library.store import SETTING_ONBOARDED, SETTING_ROOT, LibraryStore


def reset_library_state(store: LibraryStore, *, clear_root: bool = True) -> None:
    """Clear library_items, collections, watch folders, and onboarded.

    Media files on disk are left in place. Seeded collections are recreated.
    """
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
