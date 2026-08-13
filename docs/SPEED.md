# Download speed (sequential)

FrameForge never runs more than one download job at a time. Speed work is inside that single job: better format selection, aria2c multi-connection, and HLS/DASH fragment concurrency.

## Fast path (default)

- Format selector for **Best** remains `bv*+ba/b` (best video + best audio, else best combined). Per-job presets (≤1080p / 720p / 480p / audio) still override `-f`.
- When **aria2c** is on PATH, yt-dlp uses it as the external downloader with:
  - `-x 8 -s 8 -k 1M` (up to 8 connections, 1 MiB pieces)
  - `-c --allow-overwrite=true --auto-file-renaming=false` (resume-safe)
- When aria2c is not used: `concurrent_fragment_downloads = 8` on the native yt-dlp path (still one job).
- `--continue` / `continuedl` stays on so pause/resume can pick up `.part` files.

There is no multi-job parallel download.

## Gentle rate mode (opt-in)

Settings checkbox **Gentle rate mode** (`gentle_rate_mode`, default **0**).

When on, each download gets:

- `sleep_interval` 2 s / `max_sleep_interval` 5 s
- `ratelimit` 2 MiB/s

Use this **after** a bot-check or auth fail-pause, once cookies are in place, if the site still challenges you. Do not leave it on if you want maximum throughput.

The fail-pause modal points at this setting; it does not turn it on for you.

## What this does not do

- Does not start the next pending job while one is active.
- Does not raise aria2c connections beyond 8 (conservative for iGPU laptops and site friendliness).
- Does not force sleep/limit-rate on every user.
