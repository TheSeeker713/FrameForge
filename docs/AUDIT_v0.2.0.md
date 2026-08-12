# FrameForge Self-Audit — v0.2.0 (post Tier 1–4)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-12 |
| **Audited commit** | `4aa03d4de1a462897a3f75ebe4d7a37825282475` (`4aa03d4`) |
| **Branch** | `main` |
| **Repo** | https://github.com/TheSeeker713/FrameForge |
| **Auditor** | Cursor agent (code + tests; no feature changes) |
| **Prior audit** | [`docs/AUDIT_v0.1.0.md`](AUDIT_v0.1.0.md) at `fd4cad6` (~28% readiness) |

## Executive summary

**Overall readiness vs the original 11 required items: ~91%**  
(9 **PASS** + 2 **PARTIAL**; 0 **FAIL**). Previously ~**28%** at v0.1.0.

Tier 1–4 closed the former product blockers: manual download control, stable multi-select queue, cookie MVP, live progress UI shell, Upscale selected (2×), ≥2160p block, ≤720p recommendation UX, hard cancel, site/extractor on add, Open/Reveal, and a per-job error panel. The sequential invariant remains **PASS**.

Remaining honesty deductions:

1. **Live speed/ETA** — UI and `options_json` support real speed/ETA, but the **production killable subprocess download path** currently feeds `speed_str="—"` / `eta_str="—"`, so bar/% work while speed/ETA are often blank in normal GUI downloads (**PARTIAL** on item 1).
2. **Cookie “capture”** — browser opens for login and Netscape files are imported/stored/used; there is **no automated cookie scrape** from the browser session and no failure-driven auth prompt (**PARTIAL** on item 9).

### Test run recorded for this audit

| Run | Result |
|-----|--------|
| Full suite (unfiltered) | **Crashed** — Windows ORT/DirectML access violation when `test_upscale_selected_sequential_with_pending_download` called `worker._process_one()` on the main thread while the background worker loop also ran ONNX (`request_upscale_ids` → `start`). Product sequential invariant is separate from this **test hygiene** race. |
| Full suite excluding that one test | **80 passed**, 1 deselected |

Prior Tier 4 closeout claimed **81 passed** when that test was green in isolation / ordered differently. Treat concurrent ORT-on-two-threads in tests as a **remaining gap** (priority below).

---

## Confirmation: sequential invariant + SQLite queue

| Capability | Status | Evidence |
|------------|--------|----------|
| SQLite WAL DB | **Present** | [`src/frameforge/db/connection.py`](../src/frameforge/db/connection.py); `%USERPROFILE%\Downloads\FrameForge\frameforge.db` |
| Single sequential worker | **Present** | [`SequentialWorker`](../src/frameforge/queue/worker.py) — one stage at a time |
| Atomic claim; never two active stages | **Present** | [`JobRepository.claim_next_pending`](../src/frameforge/db/repository.py) `BEGIN IMMEDIATE`; refuses if any `downloading`/`upscaling` |
| Upscale-only arming | **Present** | `request_upscale_ids` sets `_only_ids = set()` so pending downloads are not claimed |
| GUI banner | **Present** | Errors if `downloading + upscaling > 1` ([`app.py`](../src/frameforge/gui/app.py)) |
| Tests | **Present** | `tests/test_phase1_worker.py`, `tests/test_phase5_final.py`, `tests/test_tier2_upscale_selected.py` (logic), `tests/test_phase1_download.py` |

**Item 11 is PASS.** Do not introduce concurrent downloads/upscales.

---

## Comparison vs original ~28% readiness

| Era | Commit | Readiness (11 items) | Snapshot |
|-----|--------|----------------------|----------|
| v0.1.0 | `fd4cad6` | ~**28%** | 1 PASS (#11), 1 PARTIAL (#7), 9 FAIL |
| v0.2.0 | `4aa03d4` | ~**91%** | 9 PASS, 2 PARTIAL (#1, #9), 0 FAIL |

Weighted score used here: PASS = 1.0, PARTIAL = 0.5, FAIL = 0 → \((9×1 + 2×0.5) / 11 ≈ 0.91\).

---

## Audit of required items (original 11)

### 1. Live progress bar (%, speed, ETA in UI) — **PARTIAL**

**Required:** Live progress bar with real %, speed, and ETA while downloading.

**Evidence — present:**

- GUI: `CTkProgressBar` + `progress_label` (`Downloading #id — N% | {speed} | ETA {eta}`) in [`gui/app.py`](../src/frameforge/gui/app.py).
- Persistence: `JobRepository.update_progress` writes `speed_bps`, `eta_seconds`, `speed_str`, `eta_str` into `options_json`.
- In-process yt-dlp hooks in [`YtDlpDownloader.build_opts`](../src/frameforge/download/ytdlp.py) emit real speed/ETA.
- Tests: `tests/test_tier1_progress.py` (in-process path).

**Evidence — gap:**

- Worker downloads use `_download_subprocess` (hard cancel). That path parses `%` but hard-codes `speed_str="—"` / `eta_str="—"` ([`ytdlp.py`](../src/frameforge/download/ytdlp.py) ~L298–305).
- Upscale progress is % only (acceptable for upscale stage).

---

### 2. Cookie / auth system (browser → cookies under data folder) — **PASS**

**Required:** Authenticate via browser; store cookies under project data folder; use for gated downloads.

**Evidence:**

- GUI **Authenticate site…** → open browser + **Import cookies.txt** ([`authenticate_site`](../src/frameforge/gui/app.py)).
- Store: [`cookies_dir()`](../src/frameforge/paths.py) → `%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt` ([`download/cookies.py`](../src/frameforge/download/cookies.py)).
- Download wiring: `resolve_cookiefile_for_url` → `YtDlpDownloader.cookiefile` ([`download/handler.py`](../src/frameforge/download/handler.py)).
- Docs: `docs/COOKIES.md`, `docs/TIER1_COMPLETE.md`.
- Tests: `tests/test_tier1_cookies.py`.

---

### 3. Better queue visual layout; scroll must not jump on refresh — **PASS**

**Evidence:**

- [`QueueList`](../src/frameforge/gui/queue_list.py): checkbox rows, badges, selection set; `scroll_fraction` / `restore_scroll` on `update_jobs`.
- Tests: `tests/test_tier1_queue_ui.py`, `tests/test_tier3_recommend.py`.

---

### 4. Upscale picker on already-downloaded videos (2×) — **PASS**

**Evidence:**

- Button **Upscale selected (2×)** → `request_upscale_ids` → `queue_for_upscale` (completed + local path → `download_completed` + `upscale=1`).
- Tests: `tests/test_tier2_upscale_selected.py`.

---

### 5. Detect 4K / ≥2160p and block upscaling with clear reason — **PASS**

**Evidence:**

- [`upscale/guards.py`](../src/frameforge/upscale/guards.py): `MIN_BLOCK_HEIGHT = 2160`; error `Blocked: source is 4K/≥2160p (height=…)`.
- Enforced in upscale handler/pipeline; job `failed` + `error`; queue badge **BLOCKED 4K+**; error panel shows reason.
- Soft note: `queue_for_upscale` does not refuse at enqueue; failure happens when upscale starts (reason still clear).
- Tests: `tests/test_tier2_4k_block.py`, `tests/test_tier3_select_recommended.py`, `tests/test_tier4_error_panel.py`.

---

### 6. Import TXT/MD only enqueues — does not auto-start — **PASS**

**Evidence:**

- GUI default `start_worker=False`; import confirm text says downloads wait for Download.
- `confirm_add` only `enqueue`s pending ([`bulk_import.py`](../src/frameforge/download/bulk_import.py)).
- Tests: `tests/test_tier1_manual_start.py`, `tests/test_phase1_bulk_import.py`.

---

### 7. Functional queue buttons — **PASS**

| Control | Wired |
|---------|--------|
| Download selected | Yes |
| Download all pending | Yes |
| Upscale selected (2×) | Yes |
| Select recommended | Yes |
| Stop after current | Yes (`disarm`) |
| Cancel selected | Yes → `cancel_job` |
| Retry failed | Yes |
| Priority + / − | Yes |
| Open folder / Reveal file | Yes |
| Refresh | Yes |
| Authenticate site… | Yes |

Tests: `tests/test_tier1_manual_start.py`, `tests/test_phase4_gui.py`, Tier 2–4 modules.

---

### 8. Add URL only enqueues (with site/extractor detection) — no auto-start — **PASS**

**Evidence:**

- `add_url` → `probe_listing_metadata` → `enqueue(title=, extractor=)`; does not arm worker ([`app.py`](../src/frameforge/gui/app.py), [`download/metadata.py`](../src/frameforge/download/metadata.py)).
- Column `jobs.extractor` (migration v3).
- Queue shows `[extractor]`.
- Tests: `tests/test_tier1_manual_start.py`, `tests/test_tier4_extractor_label.py`.

---

### 9. Sites needing human login/acceptance (browser + cookie capture) — **PARTIAL**

**Evidence — present:**

- `open_site_for_login` via `webbrowser`; user logs in; imports Netscape cookies.txt; stored under cookies dir; used by yt-dlp.

**Evidence — gap:**

- No embedded browser / automatic cookie harvest from the open session.
- No auto-prompt when a download fails due to login/bot wall.
- No live gated-site E2E in tests (path/import/wiring only).

---

### 10. Smart cookie behavior (reuse; open browser only when needed) — **PASS**

**Evidence:**

- `has_cookies` / `should_skip_auth_prompt`; GUI skips browser open when domain cookies exist (“Import to replace”).
- `resolve_cookiefile_for_url` reuses on-disk file for downloads.
- Tests: `tests/test_tier1_cookies.py`.

---

### 11. Sequential download invariant — **PASS**

See confirmation section above. Never more than one active `downloading` or `upscaling` stage under normal worker claim rules.

---

## Tier 3 / 4 extras

| Extra | Status | Evidence |
|-------|--------|----------|
| ≤720p **RECOMMENDED 2×** highlight + **Select recommended** | **PASS** | `RECOMMEND_MAX_HEIGHT=720`; [`queue_list.py`](../src/frameforge/gui/queue_list.py); button in GUI. Tests: `test_tier3_recommend.py`, `test_tier3_select_recommended.py`. Docs: `TIER3_COMPLETE.md`. |
| Hard cancel kills process tree | **PASS** | `cancel_job` → `ProcessRegistry.kill` → `taskkill /F /T`; killable yt-dlp subprocess + ffmpeg registration. Tests: `test_tier4_hard_cancel.py`. Docs: `TIER4_COMPLETE.md`. |
| Extractor/site label on add | **PASS** (bulk hostname only) | Add: yt-dlp `extract_info` skip_download. Bulk: `site_label_from_url` only (intentional inexpensive path). Tests: `test_tier4_extractor_label.py`. |
| Open folder / Reveal file | **PASS** | Buttons + [`util/reveal.py`](../src/frameforge/util/reveal.py) Explorer `/select`. Tests: `test_tier4_reveal.py`. |
| Per-job error panel | **PASS** | **Job errors / details** textbox; selection-driven. Tests: `test_tier4_error_panel.py`. |

---

## Remaining gaps (priority order)

1. **Parse/pass real speed + ETA from the killable CLI download path** (closes item 1 to PASS without losing hard cancel).
2. **Test hygiene:** stop dual-thread ONNX use (`request_upscale_ids` background loop + main `_process_one`) — prevents ORT/DML access violations in CI/full suite.
3. **Richer cookie capture** (optional): failure-driven auth prompt; clearer guided import; optional browser-extension automation (item 9 → PASS under strict reading).
4. **Pre-check 4K at `queue_for_upscale`** so blocked jobs never enter `upscaling` (UX nicety; reason already clear on fail).
5. **Bulk import full extractor probe** only if/when cheap enough (currently hostname-only by design).
6. Competitive polish still out of original 11: format picker per job, thumbnails, playlist UX, rate limits, tray, etc. (not scored here).

---

## Method notes

- Source of truth: `src/frameforge/` at commit `4aa03d4`.
- No feature code was changed in this step.
- Untracked local files `docs/porntest.md` / `docs/porntest2.md` were ignored and not committed.
- Tier completion docs consulted: `TIER1_COMPLETE.md` … `TIER4_COMPLETE.md`.
