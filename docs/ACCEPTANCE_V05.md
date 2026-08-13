# v0.5 GUI acceptance (behavior)

Primary UI is **Flet** (`python -m frameforge --gui` → `frameforge.ui_flet.app.run_gui`). CustomTkinter is not the default window. Commands go through `UiBridge` ([UI_BRIDGE.md](UI_BRIDGE.md)).

## Automated (pytest)

| # | Check | Test |
|---|--------|------|
| 1 | Settings opens once; second open focuses the same dialog | `test_settings_single_instance` |
| 2 | Retry failed → fail again → worker disarmed + fail-pause UI entry | `test_retry_fail_again_uses_same_fail_pause_handler`, `test_flet_retry_fail_again_increments_fail_pause` |
| 3 | Empty selection → no Upscale/Convert primaries | `test_floating_bar_hidden_until_selection_and_contextual_upscale` |
| 4 | Eligible completed file → Upscale available | same |
| 5 | Queue/History are `ListView`; Thumbnails `GridView` (wheel/trackpad scroll) | `test_queue_history_use_scrollable_lists` |
| 6 | Enqueue never arms the worker | `test_enqueue_does_not_arm_worker`, `test_add_url_enqueues_without_arming` |
| 7 | Full suite 100% | `python -m pytest -q` |
| 8 | This checklist | `docs/ACCEPTANCE_V05.md` |

## Manual smoke (Windows)

- [ ] `python -m frameforge --gui` opens a **light** window (bg `#F8FAFC`), not the old dark CTk toolbar
- [ ] Header: FrameForge, status pill, Settings gear, Authenticate shield
- [ ] Paste URL → **+ Add to Queue** → job is Queued; nothing downloads until **Download selected**
- [ ] Select a pending card → floating bar appears; Upscale/Convert hidden until a completed file is selected
- [ ] Failed bot-check: queue pauses; modal or card **Re-authenticate** / **Retry**; retry that fails again pauses again
- [ ] History: All / Completed / Failed; Re-download creates a new pending job
- [ ] Mouse wheel scrolls Queue, History, and Thumbnails
- [ ] Settings twice → one dialog, stays in front
- [ ] Close while downloading → three quit options still apply (Cancel / Pause / Wait)

## Invariants (unchanged)

Sequential single-active stage. No media delete on queue/history clear. Site folders under `%USERPROFILE%\Downloads\FrameForge\<site>\`.
