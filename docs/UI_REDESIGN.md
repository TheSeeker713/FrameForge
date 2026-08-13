# v0.5 UI redesign (Flet)

FrameForge’s window is **Flet 0.86.5** (Python + Flutter engine). The sequential SQLite worker, yt-dlp/aria2c, ONNX upscale, cookies, playlists, history v2, queue clear, and fail-pause stay in Python.

`python -m frameforge --gui` → `frameforge.ui_flet.app.run_gui`. CustomTkinter is **not** mixed into that window. pystray remains for the system tray if Flet has no equivalent.

## Package layout

```
src/frameforge/ui_flet/
  app.py            # FrameForgeUi, create_ui, run_gui
  theme.py          # locked light tokens
  bridge.py         # UiBridge — enqueue never arms; retry = fail-pause path
  job_view.py       # status pills, floating-bar spec, overflow ids
  components/       # job_card, floating bar, settings, modals, status_pill
```

Toolkit-agnostic leftovers: `frameforge.gui.actions`, `exit_policy`, `shortcuts` (ids), `tray`, `marshal`, `thumb_cache`.

## Tokens

| Token | Hex |
|-------|-----|
| App bg | `#F8FAFC` |
| Surface | `#FFFFFF` |
| Border | `#E2E8F0` |
| Text primary | `#0F172A` |
| Text secondary | `#64748B` |
| Accent | `#2563EB` |
| Select | `#EFF6FF` |
| Progress | `#3B82F6` |
| Success | `#10B981` / `#ECFDF5` |
| Danger | `#EF4444` / `#FEF2F2` |

Light theme only. Segoe UI. Rounded cards, pill tabs, blue primary / outline secondary.

## Action map

See [AUDIT_UI_V05.md](AUDIT_UI_V05.md). Hero: Add + Import. Header icons: Settings, Authenticate. Queue actions live on the **floating bar** (selection ≥ 1) and card overflow. Upscale / Convert appear only when the selection is eligible.

## Performance

`structural_sig` is `(id, status, title)`. Progress ticks update the active card + status pill only. Thumbnail LRU remains 64 (`frameforge.gui.thumb_cache`).

## Bridge

[UI_BRIDGE.md](UI_BRIDGE.md). Fail-pause: [FAIL_PAUSE.md](FAIL_PAUSE.md). Acceptance: [ACCEPTANCE_V05.md](ACCEPTANCE_V05.md).
