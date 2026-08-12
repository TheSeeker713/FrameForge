# Site folders complete

Per-site output directories are on `main`. Sequential worker, queue-first enqueue, pause/quit/tray, and cookie storage are unchanged except for download/upscale/convert path wiring.

See [SITE_FOLDERS.md](SITE_FOLDERS.md).

**Suite:** `python -m pytest -q` → **212 passed / 0 failed**

**Not migrated:** older files that already live in a flat `downloads\` (or other) folder. New jobs use site folders.

**Still global:** cookies, SQLite DB, thumbnails, temp, models, archive.
