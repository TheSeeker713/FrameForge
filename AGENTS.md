# FrameForge Agent Guide

FrameForge is a fully local Windows video downloader + AI video upscaler.
Target: Windows 11, AMD Ryzen 7 6800H + Radeon 680M, offline after setup.

## Identity

- Pure Python package under `src/frameforge/`
- GUI: CustomTkinter (dark, minimal, powerful)
- Downloads: yt-dlp + aria2c + FFmpeg
- Upscale: Real-ESRGAN via ONNX Runtime (DirectML preferred, CPU fallback)
- Queue: SQLite WAL, persistent across restarts
- **Sequential downloads only** — never more than one active download

## Absolute Rules

1. Work in strict Phases → Steps. Never jump ahead.
2. After every step run real tests to **100%**. Forbidden: faking, mocking, or tricking tests.
3. Scaffolding, docs, and Cursor rules before feature code (Phase 0).
4. Detect/install missing dependencies; document exact commands and versions in `docs/DEPENDENCIES.md`.
5. After every successful step: commit and push to `https://github.com/TheSeeker713/FrameForge` on `main`.
6. Prefer simplicity and reliability over complexity.
7. All user media under `%USERPROFILE%\Downloads\FrameForge\` (`downloads/`, `upscaled/`, `temp/`, `models/`, `archive/`, `frameforge.db`).
8. Preserve original audio on every upscaled video; keep metadata when possible.
9. Sequential download invariant is non-negotiable. Assert it in tests from Phase 1 onward.
10. SQLite persistence must be proven with real on-disk DB files and process restart tests.

## Competitive positioning

Unlike concurrent yt-dlp GUIs (Stacher, Parabolic, etc.) and separate upscalers (Video2X, QualityScaler), FrameForge combines sequential single-job downloads, SQLite queue, TXT/MD bulk import, and local ONNX upscaling in one AMD-friendly offline app.

## Verification commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m frameforge --version
python -m frameforge --check-env
pytest -q
.\scripts\verify_phase0.ps1
```

## Workflow

1. Implement only the current step.
2. Write/update real tests.
3. Run the full relevant suite until 100% green.
4. Commit with a precise message and push `main`.
5. Immediately continue to the next step.

See `docs/PHASES.md` for the ordered step list and `DECISIONS.md` for locked ADRs.
