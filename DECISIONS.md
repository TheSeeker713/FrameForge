# Architectural Decisions

## ADR-001: Pure Python + CustomTkinter

**Decision:** No Electron/Node. Package `frameforge` under `src/` with CustomTkinter GUI.

**Why:** Single language, simpler offline packaging on Windows, smaller agent surface area, dark-mode support sufficient for a minimal powerful UI.

## ADR-002: Sequential downloads only

**Decision:** Never more than one active download job. Hard product invariant.

**Why:** Stability on shared bandwidth, friendlier to sites, simpler queue correctness, fewer race conditions with FFmpeg post-processing.

## ADR-003: SQLite WAL persistent queue

**Decision:** All jobs live in SQLite with WAL mode under `%USERPROFILE%\Downloads\FrameForge\frameforge.db`.

**Why:** Survives app restarts and crashes; no external DB server; stdlib `sqlite3` keeps dependencies lean.

## ADR-004: Separate download and upscale stages

**Decision:** Status model separates stages (`pending` → `downloading` → `download_completed` → optional `upscaling` → `completed`, plus `failed` / `cancelled`). Optional chain via `upscale` flag. Single worker still processes one stage at a time.

**Why:** Clear progress, cancel/retry semantics, and temp cleanup boundaries.

## ADR-005: TXT/MD bulk import

**Decision:** Import http(s) URLs from `.txt` / `.md` with robust regex, preview + confirmation, dedupe against queue and archive.

**Why:** Power-user batch workflows without concurrent downloads.

## ADR-006: ONNX Real-ESRGAN + DirectML

**Decision:** Prefer `onnxruntime-directml` on AMD 680M; CPU fallback. Models under `Downloads\FrameForge\models\`.

**Why:** Local offline upscaling aligned with target hardware; avoid CUDA-only paths.

## ADR-007: Output root

**Decision:** All user media under `%USERPROFILE%\Downloads\FrameForge\`.

**Why:** Predictable location; avoid polluting C: or the git working tree.

## ADR-008: Crash recovery

**Decision:** On startup, interrupted `downloading` / `upscaling` jobs are reset to `pending` for retry (unless already `cancelled`).

**Why:** Queue must survive crashes without leaving permanent stuck states.

## ADR-009: Python 3.12 venv

**Decision:** Project venv uses Python 3.12 (meets ≥3.11 requirement).

## ADR-010: Competitive positioning

FrameForge is not a concurrent multi-download manager clone. It is a sequential, persistent, AMD-friendly downloader with integrated local AI upscaling and bulk TXT/MD import.
