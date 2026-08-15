# Download speed (sequential)

FrameForge never runs more than one download job at a time. Speed work is inside that single job: better format selection, aria2c multi-connection, HLS/DASH fragment concurrency, and yt-dlp throttle re-extract.

## Fast path (default)

- Format selector for **Best** remains `bv*+ba/b` (best video + best audio, else best combined). Per-job presets (≤1080p / 720p / 480p / audio) still override `-f`.
- `--concurrent-fragments` / `-N` default **8** (Settings: `concurrent_fragments`, range 1–32). Never starts at 1.
- `--throttled-rate 100K` so yt-dlp re-extracts when the server throttles below that floor.
- `--http-chunk-size 10M` on the native HTTP/progressive path (ignored when aria2c owns the transfer).
- When **aria2c** is on PATH, yt-dlp uses it as the external downloader with:
  - `-x 16 -s 16 -k 1M` (up to 16 connections — aria2 max — 1 MiB pieces)
  - `--file-allocation=none --summary-interval=1 --enable-color=false -c --allow-overwrite=true --auto-file-renaming=false`
  - Settings: `aria2_connections` (1–16, default 16)
- `--continue` / `continuedl` stays on so pause/resume can pick up `.part` files.
- Cookie files under `%USERPROFILE%\Downloads\FrameForge\cookies\` (e.g. `youtube.txt`) are attached only when Netscape-valid; empty/header-only files are omitted and logged as not attached.

**aria2 stays the default** when `aria2c` is on PATH, including YouTube. Do not turn it off to “fix” CDN blocks.

If aria2 hits googlevideo **HTTP 403** / exit **22**, the same job automatically retries **once** with the native yt-dlp downloader (no `--downloader aria2c`), same cookies, `-f`, `-N`, `--continue`, and output paths. Status while retrying: **CDN blocked aria2 — retrying built-in…**. The job fails only if the native attempt also fails. Category is `aria2_forbidden` (not `ffmpeg`). See [YTDLP_PARITY.md](YTDLP_PARITY.md) and [FAIL_PAUSE.md](FAIL_PAUSE.md).

There is no multi-job parallel download.

**YouTube may still server-throttle well below NIC speed** even with the same cookies + Deno as a terminal CLI. That is a site-side limit, not a FrameForge `--limit-rate`. Acceptance for v0.5.8 is matching this documented CLI recipe, not saturating the NIC. Aria2 403 is handled by native fallback, not by disabling aria2.

## Documented CLI recipe (parity)

Same cookies + Deno as the app:

```
python -m yt_dlp -N 8 --throttled-rate 100K --http-chunk-size 10M
  --downloader aria2c --downloader-args "aria2c:-x 16 -s 16 -k 1M --file-allocation=none --summary-interval=1 --enable-color=false -c --allow-overwrite=true --auto-file-renaming=false"
  --cookies %USERPROFILE%\Downloads\FrameForge\cookies\youtube.txt
  --js-runtimes deno:<path>
  --extractor-args youtube:player_client=android_vr,tv_downgraded,web_embedded,web_safari
  URL
```

`describe_cli_invocation` / the job error report shows `-N`, aria2 args, cookies path, `js_runtimes`, and `player_client` so you can paste the argv into a terminal.

## Inter-job cooldown (default 3s)

Settings **Inter-job delay** (`inter_job_delay_sec`, default **3**, range 0–60). After one download job finishes (success, fail, cancel, or pause), the worker waits this long before claiming the next **pending** download. The first job of a run starts immediately. Upscale/convert of the same file is not delayed.

This reduces bot-check pressure on bulk lists. Set to **0** to claim the next pending as soon as the current job ends.

## Optional per-job rate cap

Settings **Max download rate** (`max_download_rate`, default **0** = unlimited). Accepts `0`, an integer byte/s value, or `50K` / `2M`. Applied only when Gentle rate is off (Gentle still uses its 2 MiB/s cap).

## Gentle rate mode (opt-in)

Settings checkbox **Gentle rate mode** (`gentle_rate_mode`, default **0**).

When on, each download gets:

- `sleep_interval` 2 s / `max_sleep_interval` 5 s
- `ratelimit` 2 MiB/s (`--limit-rate`)

Use this **after** a bot-check or auth fail-pause, once cookies are in place, if the site still challenges you. Do not leave it on if you want maximum throughput. Gentle off means **no** `--limit-rate` unless Max download rate is set.

The fail-pause modal points at this setting; it does not turn it on for you.

## What this does not do

- Does not start the next pending job while one is active.
- Does not force `--limit-rate` on every user (unless Gentle rate or a max rate is set).
- Does not override YouTube’s own server throttle after EJS is solved.
