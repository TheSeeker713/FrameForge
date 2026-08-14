# Phases and Steps

Execute in order. After every step: real tests → 100% → commit + push `main`.

## Status: v0.5.1 (Flet interaction fix)

Package version is **0.5.1**. Primary GUI is Flet (`python -m frameforge --gui`). Sequential SQLite WAL worker, fail-pause, history v2, and queue clear are unchanged. See [V0.5.1_COMPLETE.md](V0.5.1_COMPLETE.md), [ACCEPTANCE_V051.md](ACCEPTANCE_V051.md), and [V0.5_UI_COMPLETE.md](V0.5_UI_COMPLETE.md).

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
