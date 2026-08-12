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

## Manual GUI checklist (Phase 4/5)

- [ ] Paste URL and add to queue
- [ ] Bulk import TXT/MD with preview confirmation
- [ ] Cancel / retry / priority
- [ ] Sequential indicator visible
- [ ] Upscale-after-download setting persists
