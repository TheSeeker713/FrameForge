# Packaging (PyInstaller, Flet)

**Layout:** one-folder `dist/FrameForge/` (not one-file). Flet’s Windows client is a Flutter tree (`flet.exe` + DLLs). One-file extraction is unreliable here; a working folder beats a broken single exe.

**Entry:** `src/frameforge/__main__.py` → same `--gui` / `--version` as `python -m frameforge`.

## Build

```powershell
.\.venv\Scripts\Activate.ps1
.\scripts\build_portable.ps1
.\scripts\smoke_packaging.ps1
```

Smoke expects `dist\FrameForge\FrameForge.exe --version` to print `frameforge <version>`.

## Flet desktop client

The spec copies `%USERPROFILE%\.flet\client\flet-desktop-full-0.86.5\flet\` into `flet-client\` (PyInstaller 6 onedir: `dist\FrameForge\_internal\flet-client\`). Runtime hook `packaging/pyi_rth_flet_view.py` sets `FLET_VIEW_PATH` to that folder so `--gui` uses the bundled client.

If the cache is missing at build time, the folder still builds; first `--gui` may download the client from GitHub into `~/.flet/client/`.

## Run

```
dist\FrameForge\FrameForge.exe --version
dist\FrameForge\FrameForge.exe --gui
```

Enqueue does not auto-start. Closing the window should exit the process (v0.5.1 shutdown path).

## Smoke recorded (v0.5.2)

| Check | Result |
|-------|--------|
| `FrameForge.exe --version` | `frameforge 0.5.2` |
| Bundled client | `dist\FrameForge\_internal\flet-client\flet.exe` present |
| `FrameForge.exe --gui` | Process started; child `flet.exe` attached; tree stopped cleanly (no stuck process) |

Source `python -m frameforge --version` prints the same version string. Enqueue-does-not-auto-start is asserted in pytest (`UiBridge`); do not arm the worker from packaging smoke.
