# Library build report

Branch `library-build`. These commits are not on `main` and have not been pushed.

| Commit | What landed |
| --- | --- |
| `3b940f0` | Build plan and the v0.6.38 test baseline |
| `7fc1683` | Migration 5, one card, many file versions |
| `7c1982c` | Queue clicks and window close no longer walk the library disk |
| `55f3b55` | An upscale is another file on the same card |
| `22a0369` | Thumbnail worker and remembered misses |
| `05de001` | Thumbnail grid and book sidebar |
| `75c97be` | Source URL and versions on the selected card |
| `2fea1af` | In-app player view, awaited stop, play, and seek |
| `c937a86` | Open, reveal, and trash without a permanent-delete fallback |
| `c0da363` | Shelf HTTP server stopped. Player and Trash packages recorded |
| `ca15e61` | Tests expect the grid |

Package version is still `0.6.38`. It was not bumped.

## Checks

Full suite after the queue, thumbnail, and model-install fixes: **721 passed, 1 skipped**.

Phase 1 tests still cover the migration timing: 3,000 items migrate in under 3 seconds, and a 10,000-row page query stays under 50 ms. A 3,000-file first paint in the real window was not measured.

## What the Library does now

The main view is a paged thumbnail grid. The default filter is All videos. Books and folders filter that grid. Files stay where they are. Remove from Library drops the database rows. Delete file asks first and uses the Recycle Bin on Windows. A failed recycle does not then delete the file. macOS and Linux use Send2Trash.

One card can hold the original, a linked file, and upscales. The detail panel shows an http or https source page, the version paths, and the job id when there is one. Play opens a view over the grid. The picture uses contain, with no fixed 16:9 box. Stop, play, pause, and seek are awaited. Escape closes the player. When the player is closed, Escape still closes other dialogs.

## Known limits

- Hover-scrub is not built.
- The sidebar has All videos, Favorites, Watch later, and books with folders. Recently added, Albums, Sites, and Watch folders are not separate sidebar sections yet.
- Resume position is remembered for the session only. It is not a database column.
- Frame step uses 24 fps when the file has no probed frame rate.
- HDR stills and a packaged Mac build were not verified.
- `packaging/frameforge.spec` now fails if the Flet desktop client cache is missing. The packager script was not run.
- Opening the Library tab can still publish completed downloads on the UI thread. The queue tick does not.
