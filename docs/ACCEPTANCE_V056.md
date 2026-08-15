# v0.5.6 GUI acceptance

Primary UI is **Flet**. Sequential worker. Enqueue never auto-starts. Clear never deletes media. Never mutate Windows Explorer / session themes.

## Themes

| # | Theme | Pass criteria | Evidence |
|---|--------|----------------|----------|
| 1 | Shell safety | No `GetForegroundWindow` in chrome; DWM not applied to foreign HWNDs | `test_shell_safety.py`, [SHELL_SAFETY.md](SHELL_SAFETY.md) |
| 2 | Innertube | YouTube argv has `player_client=android_vr,tv_downgraded,web_embedded,web_safari`; other hosts unchanged | `test_youtube_clients.py` |
| 3 | Deno/EJS | `--js-runtimes` when Deno/Node found; EJS stderr → `js_runtime` | `test_js_runtime_ejs.py` |
| 4 | Auth honesty | Firefox default; Chrome ABE text; cookies.txt path | `test_browser_cookie_import.py`, [COOKIES.md](COOKIES.md) |
| 5 | Copy error | Clipboard write recorded (FakePage + Flet Clipboard.set) | `test_error_report.py` |
| 6 | Download selected | Pending selection shows the floating **Download selected** button | `test_ui_flet_queue.py` |
| 7 | Inter-job delay | Default 3s; first job immediate | `test_inter_job_delay.py` |

## Automated (pytest)

`python -m pytest -q` → **382 passed** on the v0.5.6 docs commit (re-run to confirm).

## Manual (Windows 11 Pro)

- [ ] Drag still uses the custom title bar; Explorer look must **not** change while FrameForge is open
- [ ] Public YouTube URL without cookies: Innertube clients + Deno; formats not “only images”
- [ ] Missing Deno: `js_runtime` copyable fix, not Re-authenticate
- [ ] Chrome import: ABE error; Firefox or cookies.txt succeeds when cookies are valid
- [ ] Copy error from a failed card actually pastes
- [ ] Select pending → **Download selected** arms those ids only
- [ ] Bulk run waits ~3s between jobs (Settings 0–60)
