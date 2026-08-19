# Multi-site downloads (yt-dlp front-end)

FrameForge is a **local yt-dlp front-end**, not a YouTube-only or PornHub-only app. The same sequential worker path serves **1500–1800+ extractors plus `generic`**: site folders, per-domain cookies, format presets, aria2→native fallback, and fail-pause.

**Honest limit:** thousands of sites *via* yt-dlp extractors + generic is not a guarantee against upstream breakage, age gates, or DRM.

## Baseline argv (all hosts)

| Flag / behavior | Notes |
|-----------------|-------|
| `-f bv*+ba/b` (or per-job preset) | Progressive-only sites still work |
| `--merge-output-format mp4` | When merging |
| `--cookies` | Only when a valid Netscape file exists for the domain |
| `--ffmpeg-location`, `-N`, `--throttled-rate`, `--http-chunk-size` | Same as before |
| aria2 when on PATH | Existing native retry on aria2 403 / exit 22 |
| `--js-runtimes` | When Deno/Node is found |
| YouTube only | Existing `player_client=…` extractor-args |
| Auto impersonate list | `--impersonate chrome` when curl_cffi targets exist |

Pin: **`curl_cffi==0.13.0`** with yt-dlp **2026.07.04**. Do not bump curl_cffi alone to 0.16.x. See [ADULT_SITES.md](ADULT_SITES.md) and [DEPENDENCIES.md](DEPENDENCIES.md).

## Auto impersonate hosts

Settings → **Browser impersonate**: Auto (default) / Always / Off.

Auto uses a configurable host list (`impersonate_auto_hosts`), shipped as:

`pornhub*`, `youporn`, `redtube`, `tube8`, plus fingerprint-sensitive hosts such as `xvideos.com`, `xnxx.com`, `xhamster.com`, `spankbang.com`.

Impersonate is also forced for one recovery retry after `impersonation_missing` / TLS-fingerprint-style failures. Auto does **not** put `--impersonate` on every URL (speed/stability).

## Recovery ladder (automatic, then fail-pause)

On download failure the job records `recovery_attempts` / `recovery_tried` (“tried: …”) and retries **without opening a browser UI**:

1. **aria2 → native** (existing, inside the downloader)
2. **impersonate** once if targets exist and the error looks like missing impersonate / fingerprint
3. **Silent Firefox cookies** (same function as fail-pause **Import from Firefox / browser**): Firefox then Edge import + validate for **that job’s domain** (blocking, timeout 120s) → **interruptible backoff** → **retry** (same outcome as **Retry this job and resume queue** for the current job). Runs for every http(s) host on `auth_required` / `bot_check` / `rate_limited` / `impersonation_missing`, or `unknown` that is cookie-domain eligible (auth-like stderr, existing `cookies/<domain>.txt`, Auto-impersonate host, or impersonate already tried). Attempt names: `silent_firefox_cookies`, `backoff:N`, `retry`.
4. **Bot / rate retry without cookies** once (`bot_retry`) when cookies are not used for that failure (e.g. HTTP 429), after the same backoff.
5. **Generic extractors** once: `--use-extractors generic,default` when the error looks like extractor mismatch / unsupported webpage on an http(s) URL
6. Then **fail-pause** for auth / bot / impersonation_missing / unknown — **only if** the silent cookie path was skipped, invalid, or the retry still failed

Never auto-generic-retry or auto-cookie-retry for: `not_available`, `drm_blocked`, user cancel, `disk_space`, `db_error`, `js_runtime` (point at Deno). `output_missing` skips cookies unless the message also looks like an auth wall.

Fail-pause and the copyable error report list **tried:** attempts. FrameForge does **not** claim an in-app browser download or WebView login.

A successful silent recovery may show a brief toast: `Cookies refreshed (Firefox) — retrying…`, then `Waiting Ns before retry…` during backoff. Wait is `auto_retry_backoff_sec` (default 5, 0–60) plus `auto_retry_backoff_jitter_sec` (default 2, 0–15). Cancel/pause during the wait aborts; no retry. Sleep is on the worker thread only. **Auto recovery is not a PornHub-only path** — impersonate Auto hosts remain a separate host policy.

## DRM

yt-dlp messages in the “known DRM / will NOT be supported” family classify as **`drm_blocked`**. Actions say skip — no bypass, no Widevine/PlayReady help.

## Probe / badges

Add URL probes extractor (skip-download) and stores it on the job. Generic falls back show **`[generic]`** on the card. Bulk import still uses the hostname label only (no per-URL network probe).

## check-env

`python -m frameforge --check-env` includes `impersonation`, `extractor_count`, JS runtime, ffmpeg, and aria2.

## Out of scope (this release)

- gallery-dl (optional future note only)
- WebView2 in-app browser for auth
- DRM bypass
- Concurrent downloads

When a site breaks upstream, update **yt-dlp** in the venv and re-run `--check-env`. See [YTDLP_PARITY.md](YTDLP_PARITY.md) and [FAIL_PAUSE.md](FAIL_PAUSE.md).
