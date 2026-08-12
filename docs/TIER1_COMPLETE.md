# Tier 1 complete

**Date:** 2026-08-12  
**Final suite:** **51 passed / 0 failed**

## Commits (main)

| Step | SHA | Summary |
|------|-----|---------|
| T1.1 | `290b503` | Manual download control — idle worker; Download selected / all pending |
| T1.2 | `66af0fe` | Live progress % + speed + ETA in DB (`options_json`) and GUI bar/labels |
| T1.3 | `e6b0a4b` | Selectable queue list; selection + scroll preserved across refresh |
| T1.4 | *(this commit)* | Cookie/auth MVP — `cookies/` dir, Netscape import, yt-dlp `cookiefile`, smart skip |

## What changed

- Worker no longer auto-starts on GUI launch; enqueue/import only create `pending` jobs.
- Explicit **Download selected** / **Download all pending** / **Stop after current**.
- Progress bar + speed/ETA for the active download.
- Multi-select queue rows (checkboxes) without jump-to-top wipe.
- **Authenticate site…** opens browser + imports Netscape cookies per domain under `%USERPROFILE%\Downloads\FrameForge\cookies\`.
- Sequential invariant unchanged (single claim / one active stage).

See also: [docs/COOKIES.md](COOKIES.md).

## Remaining Tier 2 (not done)

1. Upscale picker for already-downloaded videos (select completed → queue 2× upscale).
2. Block upscaling when source height ≥ 2160p with a clear reason.
3. (Later Tier 3) Extractor detection on add, richer error panel, hard cancel of yt-dlp/aria2c, etc.
