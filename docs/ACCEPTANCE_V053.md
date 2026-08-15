# v0.5.3 GUI acceptance

Primary UI is **Flet**. Sequential worker. Enqueue never auto-starts. Clear never deletes media.

## Automated (pytest)

| # | Check | Pass criteria | Test |
|---|--------|----------------|------|
| 1 | Clear finished never removes pending | Mixed queue: pending remains | `test_clear_undo.py`, `test_queue_clear_finished.py` |
| 2 | Undo restores last clear | Flags restored; toast/chrome Undo | `test_clear_undo.py` |
| 3 | Active download shows progress + pill | ProgressBar + speed/ETA; poll `tick()` | `test_ui_flet_progress.py` |
| 4 | Failed pill visible without selection | Danger border/fill + cause row | `test_ui_flet_progress.py` |
| 5 | Retry / Download all immediate feedback | Activity note + armed pending bar | `test_ui_flet_progress.py` |
| 6 | Chrome cookie import; missing browser error | Chrome/Edge tiles; “Chrome not found / profile locked” | `test_browser_cookie_import.py`, `test_ui_flet_v051.py` |
| 7 | Authenticate does not vanish | Success stays in-modal | `test_ui_flet_v051.py` |
| 8 | Close always kills process | Idle exit; busy then second close force; pytest never `_exit`s | `test_ui_flet_shutdown.py` |
| 9 | Drag: solid window | Chrome flags opaque, reapplied; **eyes-on still required** | `test_window_chrome.py` |
| 10 | Suite | 100% | `python -m pytest -q` → **330 passed** |

## Manual (Windows — still required)

- [ ] Clear finished on a mixed queue: pending stays; Undo brings finished back
- [ ] Download all pending: header changes immediately; active card shows a bar
- [ ] Failed job is red without selecting it
- [ ] Authenticate: Chrome import; modal stays with status text
- [ ] Close: window gone within a few seconds; second X kills a stuck GUI
- [ ] **Drag title bar: solid window while moving** (v0.5.2 failed this in the field)
