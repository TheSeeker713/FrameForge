# Field migrate v0.6.3

**Date:** 2026-08-16  
**Package:** 0.6.3  
**Claim:** a **real** 3-file Move completed with `moved=3` (not unit-test-only). Cross-drive: `D:` / `C:` sources → `K:\FrameForgeProbe063\FrameForge\Library\Uncategorized`.

v0.6.2 fixed callback abort in tests. Field still failed because stale `library_items` rows (missing K: paths, `job_id` set) blocked re-move, post-move `scan_library_folder` could walk a huge bare `library_root`, and there was no per-file log. This run uses the v0.6.3 worker (purge missing rows, ingest-dir-only post-scan, `temp\library_move_*.log`).

## Command

Tiny probe files (`probe-a.mp4` … `probe-c.mp4`), `LibraryStore.set_root("K:/FrameForgeProbe063")`, `run_library_move` with a progress callback. Probe folder removed after the log was captured.

## Progress

```
progress 1/3 probe-a.mp4
progress 2/3 probe-b.mp4
progress 3/3 probe-c.mp4
SUMMARY Moved 3, failed 0, skipped 0, disk files 0, log C:\Users\jroba\Downloads\FrameForge\temp\library_move_20260816_100450.log
playable 3
```

## Log excerpt

`C:\Users\jroba\Downloads\FrameForge\temp\library_move_20260816_100450.log`

```
start library_root=K:\FrameForgeProbe063\FrameForge\Library purged_missing=0
batch jobs=3 disk=0
OK #1 src=D:\_Dev\Projects\FrameForge\_audit_tmp\probe063\dl\probe-a.mp4 dst=K:\FrameForgeProbe063\FrameForge\Library\Uncategorized\probe-a.mp4
OK #2 src=D:\_Dev\Projects\FrameForge\_audit_tmp\probe063\dl\probe-b.mp4 dst=K:\FrameForgeProbe063\FrameForge\Library\Uncategorized\probe-b.mp4
OK #3 src=D:\_Dev\Projects\FrameForge\_audit_tmp\probe063\dl\probe-c.mp4 dst=K:\FrameForgeProbe063\FrameForge\Library\Uncategorized\probe-c.mp4
```

`moved=3` >> 1. Same-drive unit tests still cover progress-callback exceptions on file 2 (file 3+ still move).

## Field follow-up for the existing youtube tree

Reset Library onboarding (or rely on purge of the 57 missing K: rows), then Move. Each file is appended to a new `Downloads\FrameForge\temp\library_move_<timestamp>.log`. If anything stops, that log names the file-2 exception.
