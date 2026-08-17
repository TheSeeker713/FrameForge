# Phases and Steps

Execute in order. After every step: real tests → 100% → commit + push `main`.

## Status: v0.6.9 (universal multi-site recovery)

Package version is **0.6.9**. Same worker path for all yt-dlp hosts: recovery ladder (native / impersonate / silent cookies / generic once), expanded Auto impersonate list, `drm_blocked`, fail-pause shows `tried: …`. See [MULTI_SITE.md](MULTI_SITE.md).

PornHub impersonate + curl_cffi 0.13.0 pin from v0.6.8 remains. Library Move field gate from v0.6.7 remains open until a real-tree log shows `OK #2+`.

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
