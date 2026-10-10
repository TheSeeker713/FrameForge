"""Migration 5: one card can hold the download and its upscale."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.connection import connect
from frameforge.db.migrate import MIGRATIONS, current_version, migrate
from frameforge.db.repository import JobRepository, utc_now
from frameforge.library.store import LibraryStore


def _v4(conn) -> None:
    now = utc_now()
    for version in range(1, 5):
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, now),
        )
    conn.commit()
    assert current_version(conn) == 4


def test_backfill_splits_download_and_upscale_and_keeps_http_urls(tmp_path: Path):
    db = tmp_path / "lib.db"
    conn = connect(db)
    _v4(conn)
    now = utc_now()
    download = tmp_path / "clip.mp4"
    download.write_bytes(b"d" * 40)
    upscale = tmp_path / "clip_x4.upscaled.mp4"
    upscale.write_bytes(b"u" * 80)
    thumb = tmp_path / "still.jpg"
    thumb.write_bytes(b"\xff\xd8" + b"t" * 40)
    conn.execute(
        """
        INSERT INTO jobs(
            url, title, status, priority, progress, upscale, created_at, updated_at,
            download_path, output_path, options_json
        ) VALUES (?, ?, 'completed', 0, 100, 1, ?, ?, ?, ?, ?)
        """,
        (
            "https://www.youtube.com/watch?v=abc",
            "Clip",
            now,
            now,
            str(download),
            str(upscale),
            '{"scale": 4, "model": "realesrgan"}',
        ),
    )
    job_id = int(conn.execute("SELECT id FROM jobs").fetchone()["id"])
    conn.execute(
        """
        INSERT INTO jobs(url, title, status, priority, progress, upscale, created_at, updated_at)
        VALUES ('javascript:alert(1)', 'Bad', 'completed', 0, 0, 0, ?, ?)
        """,
        (now, now),
    )
    bad_id = int(conn.execute("SELECT id FROM jobs WHERE title = 'Bad'").fetchone()["id"])
    conn.execute(
        """
        INSERT INTO library_items(
            job_id, title, path, thumb_path, date_added, is_private, is_favorite, watch_later
        ) VALUES (?, 'Clip', ?, ?, ?, 0, 0, 0)
        """,
        (job_id, str(download), str(thumb), now),
    )
    linked = tmp_path / "loose.mp4"
    linked.write_bytes(b"l" * 20)
    conn.execute(
        """
        INSERT INTO library_items(title, path, date_added, is_private, is_favorite, watch_later)
        VALUES ('Loose', ?, ?, 0, 0, 0)
        """,
        (str(linked), now),
    )
    conn.execute(
        """
        INSERT INTO library_items(
            job_id, title, path, date_added, is_private, is_favorite, watch_later
        ) VALUES (?, 'Script', ?, ?, 0, 0, 0)
        """,
        (bad_id, str(tmp_path / "nope.mp4"), now),
    )
    conn.commit()
    assert migrate(conn) == 5
    assert migrate(conn) == 5
    assert Path(str(db) + ".bak-v4").is_file()

    files = conn.execute(
        "SELECT role, scale, model, path FROM library_files WHERE job_id = ? ORDER BY role",
        (job_id,),
    ).fetchall()
    roles = {row["role"] for row in files}
    assert roles == {"original", "upscaled"}
    up = next(row for row in files if row["role"] == "upscaled")
    assert up["scale"] == 4
    assert up["model"] == "realesrgan"
    item = conn.execute(
        "SELECT source_url, source_site, path FROM library_items WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    assert item["source_url"] == "https://www.youtube.com/watch?v=abc"
    assert item["source_site"] == "youtube.com"
    assert Path(item["path"]).name == upscale.name
    linked_row = conn.execute(
        "SELECT role FROM library_files WHERE path = ?", (str(linked.resolve()),)
    ).fetchone()
    assert linked_row["role"] == "linked"
    bad = conn.execute(
        "SELECT source_url FROM library_items WHERE job_id = ?", (bad_id,)
    ).fetchone()
    assert bad["source_url"] is None
    thumb_row = conn.execute(
        """
        SELECT status FROM library_thumbs
        WHERE file_id = (SELECT id FROM library_files WHERE path = ?)
        """,
        (str(download.resolve()),),
    ).fetchone()
    assert thumb_row["status"] == "ok"
    originals = conn.execute(
        "SELECT item_id, COUNT(*) AS c FROM library_files WHERE role IN ('original','linked') GROUP BY item_id"
    ).fetchall()
    assert all(int(row["c"]) == 1 for row in originals)
    conn.close()


def test_three_thousand_items_migrate_in_under_three_seconds(tmp_path: Path):
    db = tmp_path / "bulk.db"
    conn = connect(db)
    _v4(conn)
    now = utc_now()
    conn.executemany(
        """
        INSERT INTO library_items(title, path, date_added, is_private, is_favorite, watch_later)
        VALUES (?, ?, ?, 0, 0, 0)
        """,
        [(f"clip {i}", str(tmp_path / f"{i}.mp4"), now) for i in range(3000)],
    )
    conn.commit()
    started = time.perf_counter()
    assert migrate(conn) == 5
    elapsed = time.perf_counter() - started
    assert elapsed < 3.0, elapsed
    assert conn.execute("SELECT COUNT(*) AS c FROM library_files").fetchone()["c"] == 3000
    assert migrate(conn) == 5
    assert conn.execute("SELECT COUNT(*) AS c FROM library_files").fetchone()["c"] == 3000
    conn.close()


def test_query_items_pages_ten_thousand_rows_quickly(tmp_path: Path):
    repo = JobRepository(tmp_path / "q.db")
    store = LibraryStore(repo)
    now = utc_now()
    store.conn.executemany(
        """
        INSERT INTO library_items(title, source_site, source_url, path, height, file_size, date_added, is_private, is_favorite, watch_later)
        VALUES (?, 'youtube.com', ?, ?, ?, ?, ?, 0, 0, 0)
        """,
        [
            (
                f"clip-{i}",
                f"https://youtube.com/watch?v={i}",
                str(tmp_path / f"clip-{i}.mp4"),
                720 if i % 2 == 0 else 1080,
                1000 + i,
                now,
            )
            for i in range(10_000)
        ],
    )
    store.conn.commit()
    started = time.perf_counter()
    page, total = store.query_items(search="clip-500", sort="title", limit=200)
    elapsed = time.perf_counter() - started
    assert total >= 1
    assert len(page) <= 200
    assert elapsed < 0.05, elapsed
    newest, _ = store.query_items(sort="date", limit=1)
    assert newest
    tall, _ = store.query_items(sort="resolution", limit=1)
    assert tall[0].height == 1080
    repo.close()
