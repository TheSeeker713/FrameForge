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

## Manual GUI checklist (Phase 4/5)

- [ ] Paste URL and add to queue
- [ ] Bulk import TXT/MD with preview confirmation
- [ ] Cancel / retry / priority
- [ ] Sequential indicator visible
- [ ] Upscale-after-download setting persists
