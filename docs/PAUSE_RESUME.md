# Pause / resume downloads

yt-dlp has **resume**, not a cooperative pause API. FrameForge pause is a hard stop that keeps partials.

## Pause

- Enabled while a job is `downloading` (or `upscaling`).
- Hard-kills the yt-dlp / aria2c / ffmpeg process tree (same registry as Cancel).
- Sets status **`paused`** (not failed, not cancelled). Progress and paths are kept.
- `.part`, aria2c control files, and yt-dlp fragment bookkeeping are **not** deleted.
- The worker **disarms** (idle). Other pending jobs do not start until you press Download or Resume.

## Resume

- Enabled while a job is `paused`.
- Returns the job to `pending` (or the upscale chain if it was paused during upscale).
- Re-invokes the download with `--continue` / `continuedl` on the same output directory.
- aria2c is passed `-c --allow-overwrite=true --auto-file-renaming=false` (no `--remove-control-file`).
- Sequential invariant still holds: only one active stage.

Some URLs restart from byte 0 if the server rejects Range requests. That is acceptable as long as partials were preserved and continue was attempted.

## Queue vs History

`paused` is **not** a history/terminal status. Cancelled jobs are distinct (progress reset, `finished_at` set).

## Quit while paused

**Pause download and quit** leaves the job `paused`. The next launch does **not** auto-resume. Use **Resume**.
