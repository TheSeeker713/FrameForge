# Original 11 items — 100% PASS

| Field | Value |
|-------|--------|
| **Date** | 2026-08-12 |
| **Gate commit** | `e9027e7` (this doc lands on the following commit) |
| **Prior audit** | [`docs/AUDIT_v0.2.0.md`](AUDIT_v0.2.0.md) at `e5d7bd9` (~91%: 9 PASS, 2 PARTIAL) |
| **Score** | **11 / 11 PASS (100%)** |

## Verification run (A4)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q tests/test_tier1_progress.py tests/test_tier1_cookies.py tests/test_a2_auth_hints.py tests/test_tier1_queue_ui.py tests/test_tier1_manual_start.py tests/test_tier2_upscale_selected.py tests/test_tier2_4k_block.py tests/test_phase1_bulk_import.py tests/test_tier3_select_recommended.py tests/test_tier3_recommend.py tests/test_tier4_hard_cancel.py tests/test_tier4_extractor_label.py tests/test_tier4_reveal.py tests/test_tier4_error_panel.py tests/test_phase1_worker.py
```

**Result: 64 passed / 0 failed.**

What closed the former PARTIALs:

- **Item 1:** `5211ca6` — parse yt-dlp/aria2c speed + ETA on the killable subprocess path (`parse_cli_progress_line`); `--progress` + aria2c `--summary-interval=1`; GUI still reads `options_json` speed/ETA.
- **Item 9:** `8df7a21` + `e9027e7` — failure-driven auth hints (no auto-open loops); error-panel **Authenticate this site…** prefilled from the failed job; Netscape import validation; smart skip / import-to-replace.

---

## The original 11

### 1. Live progress bar (%, speed, ETA in UI) — **PASS**

Killable CLI downloads now emit real speed and/or ETA (not only `%`). Parser covers yt-dlp `[download] … at …KiB/s ETA …` and aria2c `DL:…MiB ETA:…s`. Persisted via `JobRepository.update_progress` → `options_json`; GUI label `Downloading #id — N% | {speed} | ETA {eta}`.

Evidence: [`src/frameforge/download/ytdlp.py`](../src/frameforge/download/ytdlp.py) (`parse_cli_progress_line`, `_download_subprocess`); [`gui/app.py`](../src/frameforge/gui/app.py); tests `test_parse_*`, `test_subprocess_download_emits_speed_or_eta`, `test_subprocess_progress_persists_via_handler` in `tests/test_tier1_progress.py`. Hard cancel still uses the process registry (`tests/test_tier4_hard_cancel.py`).

### 2. Cookie / auth system (browser → cookies under data folder) — **PASS**

**Authenticate site…** opens the system browser; Netscape `cookies.txt` is imported to `%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt` and passed to yt-dlp as `cookiefile`.

Evidence: [`download/cookies.py`](../src/frameforge/download/cookies.py); [`docs/COOKIES.md`](COOKIES.md); `tests/test_tier1_cookies.py`.

### 3. Better queue visual layout; scroll must not jump on refresh — **PASS**

Checkbox rows, badges, selection set; `scroll_fraction` / `restore_scroll` on `update_jobs`.

Evidence: [`gui/queue_list.py`](../src/frameforge/gui/queue_list.py); `tests/test_tier1_queue_ui.py`.

### 4. Upscale picker on already-downloaded videos (2×) — **PASS**

**Upscale selected (2×)** → `request_upscale_ids` → `queue_for_upscale`.

Evidence: `tests/test_tier2_upscale_selected.py`.

### 5. Detect 4K / ≥2160p and block upscaling with clear reason — **PASS**

`MIN_BLOCK_HEIGHT = 2160`; job `failed` + error `Blocked: source is 4K/≥2160p…`.

Evidence: [`upscale/guards.py`](../src/frameforge/upscale/guards.py); `tests/test_tier2_4k_block.py`.

### 6. Import TXT/MD only enqueues — does not auto-start — **PASS**

GUI default `start_worker=False`; confirm text says downloads wait for Download.

Evidence: `tests/test_tier1_manual_start.py`, `tests/test_phase1_bulk_import.py`.

### 7. Functional queue buttons — **PASS**

Download selected / all pending, Upscale selected (2×), Select recommended, Stop after current, Cancel selected, Retry failed, Priority ±, Open folder / Reveal file, Refresh, Authenticate site…, plus **Authenticate this site…** from a failed auth job.

### 8. Add URL only enqueues (site/extractor) — no auto-start — **PASS**

`add_url` probes metadata then `enqueue`; does not arm the worker.

Evidence: `tests/test_tier1_manual_start.py`, `tests/test_tier4_extractor_label.py`.

### 9. Sites needing human login/acceptance — **PASS**

User-triggered path only (no browser auto-loop):

1. Download fails with login/bot/age/members/401/403-style signals.
2. Job stores `auth_required` + `auth_hint` in `options_json`; error panel shows **Authenticate this site / Import cookies**.
3. **Authenticate this site…** opens the dialog prefilled with that job’s URL.
4. User logs in, exports Netscape cookies.txt, imports (validated); retry.

Evidence: [`download/auth_hints.py`](../src/frameforge/download/auth_hints.py); worker annotation in [`queue/worker.py`](../src/frameforge/queue/worker.py); `tests/test_a2_auth_hints.py`. Automated cookie scrape from the live browser session remains out of scope (manual Netscape export is the supported capture method).

### 10. Smart cookie behavior — **PASS**

Reuse on-disk Netscape files; skip browser open when valid cookies exist (“Import to replace”). Header-only stubs are **not** treated as usable cookies. Empty/garbage imports are rejected.

Evidence: `tests/test_tier1_cookies.py` (`test_smart_skip_and_import`, `test_reject_empty_and_garbage_import`, `test_header_only_stub_is_not_reusable_cookies`).

### 11. Sequential download invariant — **PASS**

At most one `downloading` or `upscaling` stage. `claim_next_pending` `BEGIN IMMEDIATE`; upscale-only arming does not claim pending downloads.

Evidence: `tests/test_phase1_worker.py`; progress/handler tests assert `count_by_status("downloading") <= 1`.

---

## Not claimed here

Playlist browser UX, system tray, per-job format picker, automatic upscale, concurrent downloads, and embedded-browser cookie harvest remain deferred (not part of the original 11).
