# Phases and Steps

Execute in order. After every step: real tests → 100% → commit + push `main`.

## Status: v0.6.38 (Library books)

Package version is **0.6.38**. The Library tab shows books and folders with zero videos. Adding a video files it into a book without moving the file. Tray restore awaits `to_front`. Tool and download output is read as UTF-8. yt-dlp is 2026.8.19 or newer. First launch installs download tools only when the jobs table is empty.

Clear from queue in v0.6.35 still drops the row before the database write. v0.6.34 still saves adult hosts under `downloads/porn/<category>/` and YouTube, X, and Facebook under `downloads/social/<platform>/<category>/`.

The Library tab hosts the WebGL studio bound to the current library rows. Files stay where they are. Remove-from-library unlinks. Delete-file is a separate Recycle Bin confirm.

v0.6.10 chunked upscale / GUI-without-ONNX remains. v0.6.9 multi-site recovery remains. PornHub impersonate + curl_cffi 0.13.0 pin from v0.6.8 remains. Library Move field gate from v0.6.7 remains open until a real-tree log shows `OK #2+`.

## Phase 0 – Foundation

| Step | Work | Status |
|------|------|--------|
| 0.1 | Scaffolding, docs, Cursor rules/agents, stubs | done |
| 0.2 | Venv, install deps, models, DEPENDENCIES.md | done |
| 0.3 | Real Phase 0 verification suite 100% | done |
| 0.4 | GitHub repo create, commit, push | pending auto-review unblock |

## Phase 1 – Download engine + SQLite queue + bulk import

| Step | Work | Status |
|------|------|--------|
| 1.1–1.7 | SQLite WAL, sequential worker, yt-dlp, archive, bulk import, gate | done |

**Invariant:** never more than one job in `downloading`.

## Phase 2 – Upscale pipeline

| Step | Work | Status |
|------|------|--------|
| 2.1–2.5 | Frames, ONNX tiling, stop/resume, audio remux, gate | done |

## Phase 3 – Integration

| Step | Work | Status |
|------|------|--------|
| 3.1–3.3 | Stage orchestration, cleanup, E2E | done |

## Phase 4 – CustomTkinter GUI

| Step | Work | Status |
|------|------|--------|
| 4.1–4.5 | Dark UI, queue, bulk import, settings, worker | done |

## Phase 5 – Polish & packaging

| Step | Work | Status |
|------|------|--------|
| 5.1 | PyInstaller portable build | done |
| 5.2 | Final verification suite 100% | done |
| 5.3 | Docs and release readiness | done |
