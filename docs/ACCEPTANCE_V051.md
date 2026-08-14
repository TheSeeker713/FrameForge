# v0.5.1 GUI acceptance (interaction)

Primary UI is **Flet** (`python -m frameforge --gui` → `frameforge.ui_flet.app.run_gui`). No visual redesign. Commands still go through `UiBridge`. Enqueue never auto-starts. Sequential single-active stage.

## Automated (pytest)

| # | Check | Test |
|---|--------|------|
| 1 | Authenticate closes via X, Cancel, and `on_dismiss` | `test_authenticate_closes_via_x_cancel_and_dismiss` |
| 2 | Second Authenticate does not stack | `test_authenticate_second_open_does_not_stack` |
| 3 | Firefox success closes; error stays in modal | `test_authenticate_firefox_success_closes_error_stays` |
| 4 | cookies.txt import closes on success | `test_authenticate_cookies_txt_success_closes` |
| 5 | Settings / format / bulk / playlist close | `test_settings_and_other_modals_close` |
| 6 | Idle window close tears down without `os._exit` in tests | `test_window_close_idle_tears_down_without_os_exit` |
| 7 | Busy close opens quit modal | `test_window_close_busy_opens_quit_modal` |
| 8 | Import TXT/MD enqueues pending only | `test_import_txt_enqueues_pending_without_arming` |
| 9 | More menu items invoke real handlers | `test_more_menu_items_invoke_real_handlers` |
| 10 | More is not a nested button | `test_more_control_is_not_nested_button` |
| 11 | Queue chrome: Clear finished / Retry failed / Clear selected | `test_queue_chrome_visibility_and_handlers` |
| 12 | Opaque window, no DWM shadow (drag ghost) | `test_window_chrome_opaque_no_shadow_ghost` |
| 13 | Full suite 100% | `python -m pytest -q` |

## Manual smoke (Windows)

1. Authenticate opens and closes via **X**, **Cancel**, click-outside, and a successful Firefox/cookies action; UI stays usable.
2. Import TXT/MD → confirm → pending URLs appear; downloads do not start.
3. Select a job → **More** opens a menu → each item runs a real action.
4. Queue with completed items shows **Clear finished**; with failed shows **Retry failed**.
5. Select completed → **Clear selected**; select failed → **Retry selected**.
6. Drag the window by the native title bar — **no ghost copy**.
7. Quit/close leaves no stuck Flet server (second `python -m frameforge --gui` starts clean, no `ConnectionResetError` hang).
8. Full pytest 100%.

## Invariants (unchanged)

Sequential single-active stage. Enqueue does not arm. Clear never deletes media. BLOCKED 4K+ is completed-with-badge, not failed.
