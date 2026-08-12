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

## Manual GUI checklist (Phase 4/5)

- [ ] Paste URL and add to queue
- [ ] Bulk import TXT/MD with preview confirmation
- [ ] Cancel / retry / priority
- [ ] Sequential indicator visible
- [ ] Upscale-after-download setting persists
