# v0.5.4 GUI acceptance

Primary UI is **Flet**. Sequential worker. Enqueue never auto-starts. Clear never deletes media.

## User themes

| # | Theme | Pass criteria | Evidence |
|---|--------|----------------|----------|
| 1 | Drag visibility | Custom `WindowDragArea` title bar; native caption hidden | `test_window_chrome.py`, [UI_WINDOW_FIX.md](UI_WINDOW_FIX.md) — **eyes-on still required** |
| 2 | Pause / Cancel while downloading | Header + chrome Pause/Stop when armed or active | `test_transport_fail_pause.py` |
| 3 | Fail-pause stops bulk | Halt latch; job 2 not claimed after unknown/auth fail | `test_transport_fail_pause.py`, `test_fail_pause.py` |
| 4 | Unknown vs CLI parity | Invocation snapshot; no sticky/empty cookies; aria2c only if on PATH | `test_ytdlp_parity.py`, [YTDLP_PARITY.md](YTDLP_PARITY.md) |
| 5 | Copyable errors | Fail-pause / Authenticate / failed card Copy; non-empty report | `test_error_report.py` |
| 6 | X always quits | Idle and busy open quit dialog; Force quit always; second X force | `test_ui_flet_shutdown.py`, [UI_SHUTDOWN.md](UI_SHUTDOWN.md) |

## Automated (pytest)

| # | Check | Test |
|---|--------|------|
| 1 | Idle X opens confirm; Quit completes shutdown | `test_ui_flet_shutdown.py` |
| 2 | Busy quit offers Cancel/Pause/Wait/Stay/Force | `test_ui_flet_shutdown.py` |
| 3 | Pause/Stop visible when downloading | `test_transport_fail_pause.py` |
| 4 | Fail-pause halt even if `_armed` is set again | `test_transport_fail_pause.py` |
| 5 | argv snapshot equals `_build_cli_cmd` | `test_ytdlp_parity.py` |
| 6 | Copy report contains job id, URL, category, argv | `test_error_report.py` |
| 7 | Custom title bar is `WindowDragArea`; Close → quit | `test_window_chrome.py` |
| 8 | Suite 100% | `python -m pytest -q` → **349 passed** |

## Manual (Windows 11 Pro — still required)

- [ ] Drag the **custom** title bar (not the old OS caption): content stays solid
- [ ] During Download all: Pause leaves remaining pending; Stop cancels current and stops the run
- [ ] Bot/unknown fail: next URL does not start until Skip & resume or Retry
- [ ] Same URL that works in terminal `yt-dlp`: copy the job report and compare argv
- [ ] Copy error from fail-pause, Authenticate, and a failed card
- [ ] Window Close / custom X: quit dialog; Force quit always works
