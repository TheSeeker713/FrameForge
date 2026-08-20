# Audit: Download-all freeze (cross-check)

**Mode:** Read-only. No `src/` or test behavior changes in the commit that lands this file.  
**HEAD family:** `deea828` (silent Firefox every domain) → `05973ad` (auto-run Firefox then retry before fail-pause) → `6a50c8c` (cap silent Firefox, v0.6.13).  
**This pass does not mark the freeze fixed.**

Live Pornhub downloads were not run. No test arms Download all under a **forced hung** `yt-dlp --cookies-from-browser`. Do not read the pytest suite as proof the GUI cannot freeze.

---

## 1. Executive summary

Download all does **not** import Firefox cookies on the Flet click path. The click arms the sequential worker; silent Firefox runs later **on the worker thread**, and only **after a failed download** when `auto_cookie_recovery` is ON.

A complete GUI freeze that forces **killing the Python process** is therefore **not explained by “Download all calls Firefox on the UI thread.”** That call is absent. The close/quit watchdog never starts unless the Flet event loop can run `handle_window_close` → `_commit_quit`. If the UI thread is wedged, X does nothing and the user must kill the terminal.

The strongest code evidence for a **hard UI freeze** after the cookie-recovery commits is **thread-unsafe Flet `page.update` / `show_dialog` from the worker** (fail-pause) and, secondarily, a **cookie-import subprocess that is not in `ProcessRegistry`**, so Stop/Quit cannot kill it and the worker stays inside `Popen.communicate` until timeout or forever if timeout/kill fails.

`_action_lock` does **not** deadlock with the worker (the worker never takes it). `auto_cookie_recovery` OFF skips `next_recovery_step` → `silent_firefox_cookies`. v0.6.13 capped silent import at 60s and skipped live `extract_info` on that path; it did **not** marshal fail-pause onto the Flet loop or register the cookie PID.

---

## 2. Evidence table (claim vs code vs field)

| Claim | Code | Field fit |
|-------|------|-----------|
| Click Download all freezes immediately because it runs Firefox | **False.** Click path is arm + SQLite recover + `refresh_queue`. No `import_cookies_from_browser`. | Freeze *after* a job starts/fails still feels like “Download all froze.” |
| Auto path is the old two clicks (Firefox import → retry) without a modal | **True when recovery is eligible.** Handler: silent import → backoff → retry; modal only after that fails. | Matches product intent and earlier “manual Firefox then Retry worked.” |
| Silent Firefox is all-sites, not PH-only | **True.** `should_try_silent_cookies` / `cookie_domain_eligible` are host-agnostic (PH still extra-eligible via Auto impersonate). | Matches “every domain” commits. |
| Cap commit stopped all hangs | **Partial.** 60s timeout + file-only validate + no `unknown`+cookiefile re-import. Cookie Popen still unregistered; fail-pause still unmarshaled; no hung-import GUI test. | Freeze can still exist after `6a50c8c`. |
| Halt latch can block claims with no modal | **Yes.** `maybe_fail_pause` sets halt **before** `on_fail_pause`; callback errors are swallowed. | Queue dead, no dialog. |
| Settings OFF restores pre-recovery Download all | **Yes for silent Firefox.** `silent_cookies=silent_cookies_enabled(repo)` is False → step never `silent_firefox_cookies`. Impersonate/generic still exist. | User can A/B this. |
| Tests prove no freeze | **No.** Recovery tests mock `silent_cookie_import`. Runner timeout test is a short `python -c sleep`, not Download all + Flet. | — |

---

## 3. Call-stack diagrams

### 3.1 Download all (Flet UI thread)

```
job_card.py:340-345  "Download all pending" on_click
  → FrameForgeUi.download_all_pending          app.py:896-913
       _action_lock = True
       repo.count_by_status("pending")         SQLite (UI connection)
       UiBridge.download_all_pending           bridge.py:120-121
         SequentialWorker.request_download_all worker.py:206-213
           recover() = repo.recover_interrupted()   repository.py:773-809  **UI thread**
           start(armed=True)                   worker.py:168-180  (starts or reuses frameforge-worker)
       refresh_queue(force=True)               app.py:629-677  **UI thread, page.update**
       _action_lock = False

Also: More menu "download_all" → app.py:1114 → same download_all_pending.
create_ui(..., start_worker=True) would call request_download_all at init (app.py:194-195); production create_ui sets start_worker=False.
```

**First potentially blocking call on the click path:** `JobRepository.recover_interrupted` (`repository.py:773`) and then `refresh_queue` → SQLite list + `page.update`. SQLite connections use `PRAGMA busy_timeout=60000` (`connection.py:37`). A lock wait on the UI thread can look frozen for up to **60s**.

**Not on this path:** `silent_cookie_import`, `import_cookies_from_browser`, `interruptible_backoff`, yt-dlp cookie subprocess.

### 3.2 Failure → recovery (worker thread `frameforge-worker`)

```
SequentialWorker._loop                         worker.py:306+
  _process_one                                 worker.py:404
    claim_next_pending                         repository.py:657  BEGIN IMMEDIATE
    _run_download                              worker.py:494
      make_download_handler.handler            handler.py:51+
        dl.download(...)                       ytdlp.py (PID *is* in ProcessRegistry)
        except Exception:
          next_recovery_step(..., silent_cookies=silent_cookies_enabled(repo))
                                               handler.py:185-192, recovery.py:393-398
          if step == silent_firefox_cookies:
            progress "Importing cookies from Firefox…"
            silent_cookie_import(job.url)      handler.py:230
              recover_browser_cookies(..., timeout_sec=60, file_only=True)
                                               recovery.py:621-626
              import_cookies_from_browser      browser_import.py:123
                _default_runner Popen+communicate(timeout=remaining)
                                               browser_import.py:52-76
            [if ok] interruptible_backoff      recovery.py:269-278
            retry dl.download
          raise last_exc → job failed
      _maybe_fail_pause                        worker.py:484-492
        maybe_fail_pause → halt_after_fail     fail_pause.py:76-94, worker.py:141-146
        on_fail_pause(job)  **still on worker thread**
          UiBridge._dispatch_fail_pause        bridge.py:35-39
            FrameForgeUi._on_fail_pause        app.py:283-292
              dialogs.open → page.show_dialog + page.update
                                               dialog_host.py:60-103
```

Cookie yt-dlp is **not** `ProcessRegistry.register`’d (only the real download Popen in `ytdlp.py:762`).

---

## 4. Answers A–J

### A. Exact call stack from Download all to first potentially blocking call

1. `src/frameforge/ui_flet/components/job_card.py:344` — button click  
2. `src/frameforge/ui_flet/app.py:896` — `download_all_pending`  
3. `src/frameforge/ui_flet/bridge.py:121` — `self.worker.request_download_all()`  
4. `src/frameforge/queue/worker.py:212` — `self.recover()`  
5. `src/frameforge/db/repository.py:773` — `recover_interrupted` (SQLite SELECT/UPDATE/COMMIT on the **UI** connection)

Next blocking-ish UI work: `app.py:911` `refresh_queue(force=True)` → `page.update()` at `app.py:677`.

### B. Does Download all run cookie import or recovery on the UI thread?

**NO** (silent Firefox / cookie subprocess / backoff). Proof: `request_download_all` only recover + `start(armed=True)` (`worker.py:206-213`). `silent_cookie_import` is imported and called only from `handler.py:147-230` inside the download handler, which `_run_download` runs on `frameforge-worker` (`worker.py:179`, `494-497`).

**YES for a different recovery:** `recover_interrupted` (queue crash-recovery, not cookies) **does** run on the UI thread at arm time (`worker.py:212`).

**YES for the modal Import button** (not Download all): `_fail_pause_dialog` → `recover_bot_cookies` → `import_cookies_from_browser_for_site` on the **click/UI thread** (`app.py:339-347`, `2190-2198`), default import timeout **120s** (`browser_import.py:48,145`) and **live probe** unless `file_only` is passed (bridge `recover_bot_cookies` does not pass `file_only=True`, `bridge.py:96-113`).

### C. Does silent Firefox run only after a failed download, or also before first claim / at arm time?

**Only after a failed `dl.download` in the handler** (`handler.py:173-230`). Arm time does not call it. There is no pre-claim cookie import.

### D. On timeout, does control always return to the worker?

**Designed to return; not proven for a hung Firefox profile.**

- Silent path passes a remaining deadline into `import_cookies_from_browser` (`recovery.py:547-563`).
- `_default_runner` uses `Popen.communicate(timeout=limit)` then `kill_process_tree` (`browser_import.py:67-76`).
- Handler wraps `silent_cookie_import` in `try/except` (`handler.py:229-237`). Timeout result is `ok=False` → fail-pause path, not a retry (`handler.py:238` vs `292+`).

Caveats (control may **not** return promptly):

1. Cookie Popen is **outside** `ProcessRegistry`; Stop/cancel does not kill it. Worker stays in `communicate` until the timeout fires.
2. After `TimeoutExpired`, a second `communicate(timeout=5)` (`browser_import.py:73-75`) waits extra if `taskkill` failed.
3. If `communicate` never raises (platform/pipe edge case), there is **no other watchdog** on this Popen.
4. **No test** arms Download all with a hung cookies-from-browser. `tests/test_browser_cookie_import.py` only times out `python -c sleep`.

### E. Can halt latch block all claims while UI shows no modal?

**YES.**

- `_claims_allowed` requires armed **and** not `_fail_pause_halt` (`worker.py:151-153`).
- `maybe_fail_pause` calls `halt_after_fail()` **before** returning True (`fail_pause.py:86-94`).
- Worker then calls `on_fail_pause`; **exceptions are swallowed** (`worker.py:488-492`).
- If `dialogs.open` / `page.update` throws or hangs without painting, halt is already set and claims stay blocked.
- Download all **does** clear halt (`worker.py:209-211`, `start` at `168-173`) — but only if the user can click it (event loop alive).

### F. Can `_action_lock` + worker create a deadlock?

**No evidence of a lock-order deadlock.** `_action_lock` is a boolean on `FrameForgeUi` (`app.py:271,896-913`). The worker never reads it. It is always cleared in `finally`. It only drops duplicate UI clicks while recover/refresh runs.

**Related (not `_action_lock`):** worker-thread `page.update` vs UI-thread `page.update` / SQLite `busy_timeout` can freeze Flet without sharing `_action_lock`.

### G. With `auto_cookie_recovery` OFF, is Download all free of silent Firefox?

**YES.** Proof:

- Settings write `auto_cookie_recovery` (`settings_dialog.py:281-283`).
- `silent_cookies_enabled` requires that setting ON (`recovery.py:218-222`).
- Handler passes `silent_cookies=silent_cookies_enabled(repo)` into `next_recovery_step` (`handler.py:192`).
- `next_recovery_step` only returns `SILENT_FIREFOX_COOKIES` when `silent_cookies` is true (`recovery.py:393-398`).

Download all still recover-interrupts, claims, and downloads. Impersonate / generic recovery can still run. Cookie **modal** Import still calls Firefox if the user clicks it.

### H. Why would the user need to kill the terminal (not just close the window)?

1. `attach_page` sets `win.prevent_close = True` (`app.py:2601-2602`). X is intercepted; quit is `handle_window_close` → dialog or `_commit_quit` (`app.py:2516-2577`).
2. `_commit_quit` is what arms `schedule_hard_exit` (`app.py:2561`, `process_tree.py:114-121`). If the **Flet loop never runs** the close handler, **no watchdog**, `prevent_close` stays, window/process remain.
3. `worker.stop(timeout=0.2)` (`app.py:2575`) will **not** wait out a 60s cookie import; that only matters **after** `_commit_quit` runs. Frozen UI ⇒ never gets there.
4. Cookie import PID is not in `ProcessRegistry`, so even a working Stop may leave yt-dlp cookies-from-browser alive until timeout.

This is a **code** explanation (event loop + prevent_close + late watchdog). Not RustDesk, not “environment,” unless those only made Firefox’s profile lock (which still should be bounded if timeout works).

### I. Top 3 root-cause hypotheses (ranked by evidence)

1. **Fail-pause (and/or tick) mutates Flet from a non-UI thread, wedging the event loop.**  
   Worker: `_dispatch_fail_pause` → `_on_fail_pause` → `dialogs.open` → `page.update` (`bridge.py:35-39`, `app.py:283-292`, `dialog_host.py:98-101`) **with no `page.run_task` marshal**. CustomTkinter GUI **does** marshal (`gui/app.py:58-59`). Tick fallback can also call `tick()` on a `threading.Timer` thread if `page.run_task` fails (`app.py:830-840`). Frozen loop + `prevent_close` ⇒ kill terminal. Fits “after cookie recovery”: fail-pause/import now happen automatically after the first Download-all job fails.

2. **Silent Firefox Popen unbounded or unkillable; worker stuck in `communicate`; UI looks dead (progress stuck on “Importing cookies…”); quit cannot kill that PID.**  
   `browser_import.py:66-76`; not registered (`ytdlp.py:762` vs cookie helper). v0.6.13 *intends* 60s; if timeout/kill fails on a locked `cookies.sqlite`, this matches “must kill Python.” Weaker for **instant** freeze on click (import is post-failure).

3. **UI-thread SQLite `busy_timeout` (60s) during `recover_interrupted` / `refresh_queue` while the worker holds `BEGIN IMMEDIATE`, and/or `recover_interrupted` resetting an in-flight `downloading` row so a second job is claimed (sequential invariant break, machine-level stall).**  
   `connection.py:17,37`; `repository.py:669,773-809`; `worker.py:212`. Fits a **second** Download all during an active job better than the first click on an idle queue.

**Rejected as primary:** “Download all runs Firefox on the UI thread” — not in the click stack (B).

### J. Minimal fix plan (do not implement here)

Ordered; sequential invariant called out.

1. **Marshal fail-pause (and any `page.update`) onto the Flet loop** — same idea as CTk `marshal_ui`. Worker only sets halt + payload; UI tick or `page.run_task` opens the modal. **Risk to sequential invariant: none.** Highest leverage for “kill the terminal.”
2. **Register cookie-import Popen in `ProcessRegistry` (or a dedicated cookie PID)** and poll `_stop` / cancel during import; `kill_active_processes` must kill it. Keep 60s timeout. **Risk: none if still one worker thread; do not start a second download while import runs.**
3. **Do not call `recover_interrupted` on the UI thread from Download all** — move it to the worker before the next claim, or skip it when a stage is already active so a second click cannot demote `downloading` → `pending` and claim another job. **Risk if skipped blindly: crashed `downloading` rows stay stuck; if always run while handler is live: breaks sequential invariant (two downloads).** Prefer: recover only rows whose handler is not this process’s in-flight job.
4. **Optional:** lower UI `busy_timeout` or use a short timeout for arm/refresh so the click path cannot sit 60s. **Risk: more `database is locked` errors; must retry, not fail the queue.**
5. **Test (required before calling freeze fixed):** Flet-free worker test: arm Download all, force hung cookie runner that ignores timeout unless killed, assert halt/fail-pause and that a later arm still claims; plus a test that fail-pause callback is not invoked on the worker thread (or is marshaled). **Do not claim GUI freeze gone without a hung-import + UI-thread assertion.**

---

## 5. What the “cap silent Firefox” commit did and did not cover

**Did (`6a50c8c`, v0.6.13):**

- Silent import total budget 60s; `_default_runner` kill tree on `TimeoutExpired`.
- Silent validate `file_only=True` (no live `extract_info` on that path) (`cookie_validate.py:116`, `recovery.py:621-626`).
- `unknown` no longer re-imports merely because a Netscape file exists (`recovery.py` `cookie_domain_eligible`).
- Halt clear on `start(armed=True)` / Stop / fail-pause Stop; recovery exceptions logged and must not kill `_loop`.
- Settings OFF skips silent Firefox (G).

**Did not:**

- Move cookie import off the worker (it was already off the UI thread for auto path).
- Marshal Flet fail-pause / `page.update`.
- Register cookie subprocess in `ProcessRegistry`.
- Make cookie import abort on `_stop` before timeout.
- Stop `recover_interrupted` on the Download-all UI click.
- Add a test that arms Download all under a hung cookies-from-browser **and** a live Flet page.
- Change manual modal import (still 120s + probe on UI thread).

---

## 6. Recommended minimal fix

Do **(1) marshal fail-pause to Flet** and **(2) register/kill cookie Popen** first. Then **(3)** stop UI-thread `recover_interrupted` from racing an in-flight download. Then add the hung-import test. Do not add more recovery steps. Do not implement in this commit.

---

## 7. Explicit: no product code in this commit

This file is documentation only. No `src/` edits, no settings schema, no version bump, no test behavior changes.
