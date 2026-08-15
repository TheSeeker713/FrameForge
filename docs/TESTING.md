# Testing

## Absolute bar

Every step requires **100%** real pass. No faking, mocking, or tricking tests to force green.

## Phase 0

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q tests/test_phase0_foundation.py
.\scripts\verify_phase0.ps1
```

## Fixtures (Phase 1+)

Use short **public domain / Creative Commons** clips only.

Documented sample URLs for automated tests:

- `https://samplelib.com/lib/preview/mp4/sample-5s.mp4`
- `https://samplelib.com/lib/preview/mp4/sample-10s.mp4`

SQLite persistence tests must use **real on-disk** DB files and process restart — not in-memory-only for persistence claims.

Sequential invariant: assert never more than one job in `downloading` at a time; assert non-overlapping download execution windows.

## Full suite (B2 gate)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

**2026-08-12:** **97 passed / 0 failed** (no quarantines). Upscale tests must not run ONNX on the background worker loop and `_process_one` in the same process — pass `request_upscale_ids(..., start_loop=False)` when draining on the calling thread (DirectML is not dual-thread safe).

## v0.4 Prompt 1 baseline

- **SHA:** `58a8262ec086a2ee3dae13812fe15dd79de0d356`
- **Suite:** `python -m pytest -q` → **116 passed / 0 failed**
- Starting point for pause/resume, quit policy, tray, and browser cookie import.

## v0.4.0 Prompt 1 complete

- **Suite:** `python -m pytest -q` → **157 passed / 1 skipped / 0 failed**
- Skip: live sample clip can finish before the pause/cancel sampling window (not a quarantine).

## v0.4 Prompt 2 baseline

- **SHA:** `ae10f77acc8739771c4a9904043454ebae76bff8`
- **Suite:** `python -m pytest -q` → **158 passed / 0 failed**
- Prompt 1 APIs present: `paused`, exit policy choices, tray service, cookies-from-browser helper.

See [PLAYLISTS.md](PLAYLISTS.md), [FORMATS_AND_CONVERT.md](FORMATS_AND_CONVERT.md), [RESOURCES.md](RESOURCES.md), [SHORTCUTS.md](SHORTCUTS.md). Prompt 1 docs ([PAUSE_RESUME.md](PAUSE_RESUME.md), [TRAY_AND_QUIT.md](TRAY_AND_QUIT.md), [COOKIES.md](COOKIES.md)) remain valid.

## v0.4.0 complete (Prompt 1 + Prompt 2)

- **Suite:** `python -m pytest -q` → **192 passed / 0 skipped / 0 failed**
- See [V0.4_COMPLETE.md](V0.4_COMPLETE.md).

## v0.4.2 queue clear / History v2 / fail-pause / speed

- **Suite:** `python -m pytest -q` → **261 passed / 0 skipped / 0 failed**
- See [V0.4.2_COMPLETE.md](V0.4.2_COMPLETE.md), [QUEUE_CLEAR.md](QUEUE_CLEAR.md), [HISTORY_V2.md](HISTORY_V2.md), [FAIL_PAUSE.md](FAIL_PAUSE.md), [SPEED.md](SPEED.md).

## v0.5.3 P0 field recovery

- **Suite:** `python -m pytest -q` → **330 passed / 0 skipped / 0 failed**
- See [V0.5.3_COMPLETE.md](V0.5.3_COMPLETE.md), [ACCEPTANCE_V053.md](ACCEPTANCE_V053.md).

## v0.5.2 hover, bot-check, packaging

- **Suite:** `python -m pytest -q` → **314 passed / 0 skipped / 0 failed**
- See [ACCEPTANCE_V052.md](ACCEPTANCE_V052.md), [BOT_CHECK_PLAYBOOK.md](BOT_CHECK_PLAYBOOK.md), [PACKAGING.md](PACKAGING.md).

## v0.5.1 Flet interaction fix

- **Suite:** `python -m pytest -q` → **298 passed / 0 skipped / 0 failed**
- See [V0.5.1_COMPLETE.md](V0.5.1_COMPLETE.md), [ACCEPTANCE_V051.md](ACCEPTANCE_V051.md), [AUDIT_UI_V051.md](AUDIT_UI_V051.md), [UI_SHUTDOWN.md](UI_SHUTDOWN.md), [UI_WINDOW_FIX.md](UI_WINDOW_FIX.md).

## v0.5.0 Flet GUI rewrite

- **Suite:** `python -m pytest -q` → **285 passed / 0 skipped / 0 failed**
- See [V0.5_UI_COMPLETE.md](V0.5_UI_COMPLETE.md), [UI_REDESIGN.md](UI_REDESIGN.md), [ACCEPTANCE_V05.md](ACCEPTANCE_V05.md), [UI_BRIDGE.md](UI_BRIDGE.md).

## Site folders

See [SITE_FOLDERS.md](SITE_FOLDERS.md). New downloads use `FrameForge\<site_key>\`; cookies/DB/thumbnails stay global.

- **Suite:** `python -m pytest -q` → **212 passed / 0 failed**

## Bulk TXT/MD import

Parser: `frameforge.download.bulk_import`. Accepts `.txt` / `.md` (UTF-8 or UTF-16). Extracts every `http(s)://` URL (YouTube watch, `/shorts/`, youtu.be, query strings, markdown `[text](url)`, inline). Preview dialog shows New URLs vs duplicates; confirm only enqueues **pending** (does not start downloads).

Fixtures: `tests/fixtures/youtube_bulk.md`, `tests/fixtures/youtube_md_links.md`, `tests/fixtures/bulk_urls.txt`.

## Manual GUI checklist (Phase 4/5)

- [ ] Paste URL and add to queue
- [ ] Bulk import TXT/MD with preview confirmation
- [ ] Cancel / retry / priority
- [ ] Sequential indicator visible
- [ ] Upscale-after-download setting persists
