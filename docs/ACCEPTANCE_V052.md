# v0.5.2 GUI acceptance

Primary UI is **Flet** (`python -m frameforge --gui` and `dist\FrameForge\FrameForge.exe --gui`). Sequential worker. Enqueue never auto-starts.

## Automated (pytest)

| # | Check | Pass criteria | Test |
|---|--------|----------------|------|
| 1 | Hover elevation | Cards/buttons have hover shadow/elevation specs; window stays opaque, `window.shadow=False` | `test_ui_flet_elevation.py` |
| 2 | Bot classify | Fixture stderr → category + non-empty cause/tail | `test_bot_check_classify.py` |
| 3 | Bot recover | Import cookies → validate → retry+resume; no arm on import | `test_cookie_validate.py` |
| 4 | Fail-pause retry | Fail again → disarm + same UI entry | `test_acceptance_v05.py`, `test_ui_bridge_fail_pause.py` |
| 5 | Import / More / Auth close | v0.5.1 behaviors still green | `test_ui_flet_v051.py` |
| 6 | PyInstaller spec | Flet hiddenimports + one-folder COLLECT | `test_packaging_spec.py` |
| 7 | Suite | 100% passed | `python -m pytest -q` → **314 passed** |
| 8 | Dead clicks | Fail-pause five actions, chrome, floating bar, Settings Save/Cancel have `on_click` | `test_ui_flet_dead_clicks.py` |

## Manual / recorded smoke (Windows)

- [ ] Hover a job card and **+ Add to Queue** — visible lift; drag the native title bar — **no ghost** (widget specs automated; visual lift is eyes-on)
- [x] Bot classify + validate-before-resume — pytest (`test_bot_check_classify.py`, `test_cookie_validate.py`)
- [x] `dist\FrameForge\FrameForge.exe --version` → `frameforge 0.5.2`
- [x] `FrameForge.exe --gui` started `FrameForge.exe` + child `flet.exe`; process tree stopped cleanly


## Invariants

Sequential single-active stage. Clear never deletes media. BLOCKED 4K+ is completed-with-badge. Opaque `#F8FAFC` window, no OS DWM shadow.
