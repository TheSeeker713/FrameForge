# FrameForge Self-Audit — v0.1.0

| Field | Value |
|-------|--------|
| **Date** | 2026-08-12 |
| **Audited commit** | `fd4cad6821d606b4a2155b15e6ca4ad1e963b72b` |
| **Branch** | `main` |
| **Repo** | https://github.com/TheSeeker713/FrameForge |
| **Auditor** | Cursor agent (code + behavior review; no feature changes) |

## Executive summary

**Overall readiness vs required UI/UX + auth gaps: ~28%.**

Core download/queue/upscale plumbing exists and the **sequential download invariant** and **SQLite WAL queue** are real and tested. The product is **not** competitive with mature yt-dlp GUIs (Stacher, Parabolic, ArcDLP, VidBee) on live progress, cookies/auth, queue selection UX, or manual download control.

### Biggest blockers (Tier 1)

1. **Worker auto-starts on GUI launch** — enqueue and bulk import immediately begin downloading; violates “queue only” requirements (#6, #8).
2. **No cookie / browser auth system** — gated, age-restricted, and bot-blocked sites cannot be authenticated (#2, #9, #10).
3. **No true live progress UI** — no progress bar; no speed/ETA in UI or progress callback (#1).
4. **Queue is a wiped textbox** — poor layout; scroll jumps to top every 1s refresh (#3).
5. **Missing queue actions** — no Download selected / Download all pending; weak selection model (#7).
6. **No post-download upscale picker** and **no ≥2160p upscale block** (#4, #5).

---

## Confirmation: sequential invariant + SQLite queue

| Capability | Status | Evidence |
|------------|--------|----------|
| SQLite WAL DB | **Present** | [`src/frameforge/db/connection.py`](../src/frameforge/db/connection.py) `PRAGMA journal_mode=WAL`; schema in [`migrate.py`](../src/frameforge/db/migrate.py); path `%USERPROFILE%\Downloads\FrameForge\frameforge.db` |
| Single sequential worker | **Present** | [`src/frameforge/queue/worker.py`](../src/frameforge/queue/worker.py) |
| Atomic claim + never two `downloading` | **Present** | [`JobRepository.claim_next_pending`](../src/frameforge/db/repository.py) uses `BEGIN IMMEDIATE` and refuses if any `downloading`/`upscaling` |
| Tests | **Present** | `tests/test_phase1_sqlite.py`, `tests/test_phase1_worker.py`, `tests/test_phase5_final.py` |

**Item 11 below is PASS.** Do not regress this while fixing auto-start (paused/manual start must still use the same single worker).

---

## Audit of required items

### 1. Live progress bar (percentage / speed / ETA in UI) — **FAIL**

**Required:** Live progress bar with real %, speed, and ETA visible while downloading.

**Evidence:**

- GUI has **no** `CTkProgressBar` (or any progress bar widget). Queue is a plain [`CTkTextbox`](../src/frameforge/gui/app.py) showing text like `{progress:.1f}%`.
- Refresh every 1s via `_tick` → `refresh_queue()` ([`app.py`](../src/frameforge/gui/app.py) L177–198).
- Backend progress callback is **percentage-only**:
  - [`YtDlpDownloader.build_opts` `_hook`](../src/frameforge/download/ytdlp.py) L63–72 reads `downloaded_bytes` / `total_bytes` only.
  - Does **not** read or persist `speed`, `eta`, `_speed_str`, `_eta_str`, or fragment counts from the yt-dlp hook dict.
  - [`ProgressCb = Callable[[float], None]`](../src/frameforge/download/ytdlp.py) L13 — float pct only.
  - [`JobRepository.update_progress`](../src/frameforge/db/repository.py) stores a single `progress REAL`; no speed/ETA columns.
- With **aria2c** as external downloader, yt-dlp progress hooks are often coarse/incomplete; no dedicated aria2c progress parsing either.

**Gap vs mature GUIs:** Stacher/Parabolic show active download row with bar + speed + ETA.

---

### 2. Cookie / auth system (browser → cookies under data folder) — **FAIL**

**Required:** User authenticates any site via browser; cookies collected and stored under project data folder for gated / age-restricted / bot-blocked downloads.

**Evidence:**

- No `cookies/` subdirectory in [`paths.SUBDIRS`](../src/frameforge/paths.py) (only `downloads`, `upscaled`, `temp`, `models`, `archive`).
- No cookie module under `src/frameforge/` (no files matching cookie/browser/login flows).
- [`YtDlpDownloader.build_opts`](../src/frameforge/download/ytdlp.py) never sets `cookiefile`, `cookiesfrombrowser`, or related opts.
- GUI has no “Login / Get cookies” control ([`app.py`](../src/frameforge/gui/app.py)).
- `.cursor/rules/safety.mdc` warns not to commit cookies — policy only, not an implementation.

**Gap vs mature GUIs:** Browser cookie import / Netscape cookie file is table-stakes for YouTube age gates and many adult/membership sites.

---

### 3. Better queue visual layout; scroll must not jump on refresh — **FAIL**

**Required:** Improved queue layout; scrolling must not jump to top on update.

**Evidence:**

- Queue UI is a monospaced dump into `CTkTextbox` ([`refresh_queue`](../src/frameforge/gui/app.py) L177–188):
  - `queue_box.delete("1.0", "end")` then `insert("1.0", ...)` **every refresh**.
- `_tick` calls `refresh_queue()` every **1000 ms** (L196–198), so any user scroll position is continuously reset to top.
- No list/tree widget, no multi-select checkboxes, no per-row widgets, no scroll-position preservation (`yview`, selection indices).
- “Selected” job is inferred from text insert cursor on a line (`_selected_job_id`) — fragile and not multi-select.

**Gap vs mature GUIs:** Stable virtualized/list views with selection that survives progress ticks.

---

### 4. Upscale picker on already-downloaded videos (2×) — **FAIL**

**Required:** Select one or more completed downloads and queue 2× upscale.

**Evidence:**

- Settings only expose **“Upscale after download”** boolean ([`open_settings`](../src/frameforge/gui/app.py) L128–146) applied at enqueue time.
- No UI action to pick completed jobs / files from `downloads/` and enqueue upscale-only work.
- Upscale handler expects an existing `download_path` ([`upscale/handler.py`](../src/frameforge/upscale/handler.py)) but is only reached via worker stage when `job.upscale` was set before/during download pipeline ([`worker.py`](../src/frameforge/queue/worker.py) L74–77, L93–96).
- No “2×” scale picker in GUI (pipeline uses whatever ONNX scale the model implies).

---

### 5. Detect 4K / ≥2160p and block upscaling with clear reason — **FAIL**

**Required:** Videos at 4K or height ≥2160 must be blocked from upscaling with a clear reason.

**Evidence:**

- Repo-wide search: no `2160`, no `4K`/`4k` upscale guard in `src/`.
- [`UpscalePipeline.run`](../src/frameforge/upscale/pipeline.py) and [`OnnxUpscaler`](../src/frameforge/upscale/onnx_upscaler.py) do not check input resolution before processing.
- [`video_size`](../src/frameforge/upscale/ffmpeg_utils.py) exists and could support a guard but is unused for blocking.
- No user-facing error string for “blocked: source is 4K / ≥2160p”.

---

### 6. Import TXT/MD must only enqueue — must not auto-start downloads — **FAIL**

**Required:** Import enqueues URLs only; does not automatically start downloads.

**Evidence:**

- Import path itself only calls `confirm_add` → `repo.enqueue(..., status='pending')` ([`bulk_import.py`](../src/frameforge/download/bulk_import.py), [`import_file`](../src/frameforge/gui/app.py) L106–126). **Enqueue-only at API level.**
- However, GUI default constructs worker and **starts it immediately**:
  - [`FrameForgeApp.__init__(..., start_worker: bool = True)`](../src/frameforge/gui/app.py) L25, L78–80: `build_worker` + `self.worker.start()`.
  - [`SequentialWorker.start`](../src/frameforge/queue/worker.py) → `_loop` → `claim_next_pending` → download.
- Therefore, with the normal GUI entry (`python -m frameforge --gui`), importing a list **will auto-start** the next pending job within the poll interval (~50ms worker loop).

**Observed design contradiction:** “queue then decide” UX is impossible while the worker is always running.

---

### 7. Functional queue buttons (Download selected / all pending, Cancel, Retry, etc.) — **PARTIAL**

**Required:** Functional controls including Download selected, Download all pending, Cancel, Retry, etc.

**Evidence — present:**

| Control | Location |
|---------|----------|
| Cancel selected | [`cancel_selected`](../src/frameforge/gui/app.py) L157–162 |
| Retry failed (all failed → pending) | [`retry_failed`](../src/frameforge/gui/app.py) L164–167 |
| Priority + / − | L169–175 |
| Refresh | L72–73 |

**Evidence — missing:**

- No **Download selected**
- No **Download all pending**
- No **Pause worker / Stop after current**
- No **Upscale selected**
- No multi-select; “selected” is cursor-line only
- Cancel on an actively downloading job relies on progress_cb seeing `cancelled` ([`handler.py`](../src/frameforge/download/handler.py) L33–36); there is no hard abort of yt-dlp/aria2c process — cancel mid-download is best-effort / delayed

Because the worker auto-runs, “Download all pending” is effectively always-on, which is the opposite of an explicit button model.

---

### 8. Adding a URL must only add to queue (with site/extractor detection) — no auto-start — **FAIL**

**Required:** Add URL → queue only, with site/extractor detection; do not auto-start download.

**Evidence:**

- [`add_url`](../src/frameforge/gui/app.py) L93–104 only `enqueue`s URL string; **no** `extract_info`, no extractor/site label stored on the job at add time.
- Job schema has no `extractor` column on `jobs` (only on `download_archive` after success) — [`migrate.py`](../src/frameforge/db/migrate.py).
- [`YtDlpDownloader.extract_info`](../src/frameforge/download/ytdlp.py) exists but is **not called** from GUI add/import.
- Same auto-start problem as #6: running worker claims new `pending` jobs immediately.

---

### 9. Sites requiring human acceptance / login (browser open + cookie capture) — **FAIL**

**Required:** Support flows that need human acceptance/login via browser open + cookie capture.

**Evidence:**

- No browser launcher (no `webbrowser` usage in app flows, no Playwright/Selenium/webview cookie capture).
- No UI to open a site and wait for user confirmation.
- No integration to feed captured cookies into yt-dlp for the next attempt.

---

### 10. Smart cookie system (reuse per domain; open browser only when needed) — **FAIL**

**Required:** If cookies exist for domain, skip collection; open browser only when needed (ideally once per session per domain).

**Evidence:**

- No per-domain cookie store under data folder.
- No session cache of “already prompted for domain X”.
- No logic on download failure (e.g. sign-in / bot check) to trigger cookie collection.

---

### 11. Sequential download invariant (never more than one active download) — **PASS**

**Evidence:**

- [`claim_next_pending`](../src/frameforge/db/repository.py) L209–254 refuses claim if any job is `downloading` or `upscaling`.
- Worker processes one stage at a time ([`worker.py`](../src/frameforge/queue/worker.py)).
- GUI banner warns if `downloading > 1` ([`app.py`](../src/frameforge/gui/app.py) L189–194).
- Automated tests assert non-overlapping execution and single `downloading` claim.

**Note:** Keep this invariant when introducing manual start — the fix is “worker idle until user starts,” not concurrent downloads.

---

## Additional competitive gaps (vs Stacher / Parabolic / ArcDLP / VidBee)

| Gap | Notes |
|-----|--------|
| Format / quality picker per job | Only global settings string `format_preference` |
| Thumbnail / rich metadata in queue | Title/url text only |
| Subtitle / chapter options | Not exposed in GUI |
| Open output folder / reveal file | Missing |
| Per-job logs / error detail panel | `error` column exists; UI does not surface it in queue text |
| Bandwidth / rate limit settings | Not present |
| Playlist expansion UX | Not present |
| System tray / minimize behavior | Not present |
| True multi-select + batch actions | Not present |
| Cookie manager UI | Not present |
| Download speed graph / history | Not present |

---

## Fix priority

### Tier 1 — correctness / product blockers

1. **Manual download control:** default worker **stopped**; enqueue/import only create `pending` jobs; add **Download selected** and **Download all pending** (still sequential).
2. **Cookie/auth MVP:** cookies dir under FrameForge data root; Netscape cookiefile per domain; GUI “Authenticate site…”; pass `cookiefile` into yt-dlp; smart skip if file exists.
3. **Live progress:** persist speed + ETA (DB columns or `options_json`); progress bar + labels in UI; improve hook (and aria2c-aware progress if needed).
4. **Stable queue widget:** replace textbox wipe with list/tree that preserves scroll + selection on refresh.

### Tier 2 — upscale product rules

5. **Upscale selected completed downloads** (multi-select → queue upscale stage / jobs at 2×).
6. **≥2160p detection + block** with clear UI/DB error reason before upscale starts.

### Tier 3 — polish / parity

7. Extractor/site detection on add (store on job; show in queue).
8. Surface job `error` in UI; open-folder actions; richer per-job format options.
9. Harder cancel (terminate yt-dlp/aria2c subprocess).
10. Session-scoped “already authenticated domain” memory on top of on-disk cookies.

---

## Concrete next implementation steps (do not implement in this audit)

1. Add job lifecycle flag or worker mode: `idle` vs `running`; GUI start/stop; **do not** call `worker.start()` on app init by default.
2. Add buttons: Download selected, Download all pending; wire to claim only when user requested (or temporarily start worker until idle).
3. Extend progress model: `speed_bps`, `eta_seconds` (columns or JSON); update yt-dlp hook; add `CTkProgressBar` + labels; preserve queue scroll/selection.
4. Replace `CTkTextbox` queue with selectable rows (e.g. `CTkScrollableFrame` of row frames or tk `ttk.Treeview`).
5. Create `paths.cookies_dir()`, cookie store API, browser-assisted capture flow, yt-dlp `cookiefile` wiring, domain reuse checks.
6. Add “Upscale selected (2×)” for `completed` jobs with `download_path`; probe height via ffprobe; refuse ≥2160p with explicit error.
7. On Add URL: optional lightweight `extract_info` (or yt-dlp `list_extractors`/URL matching) to set title/extractor without downloading.
8. Expand tests: no download until explicit start; cookiefile passed when present; 4K upscale blocked; scroll position regression test if feasible.

---

## Method notes

- Source of truth: tree under `src/frameforge/` at commit `fd4cad6`.
- No feature code was changed in this step.
- Behavior of auto-start is deduced from GUI default `start_worker=True` + always-on worker loop (not from a separate product setting).
- Untracked local file `docs/porntest.md` was observed in the working tree and was **not** included in this audit commit.
