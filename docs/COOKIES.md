# Cookies / authentication

FrameForge stores per-domain Netscape cookie files under:

`%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt`

Authenticate and Settings show that resolved folder and list domain `*.txt` files found. **Open cookies folder** launches Explorer on that directory only (no theme or DWM changes).

## Import from browser (v0.5.6+)

**Auto path (v0.6.13):** Auto recovery runs for **every domain**, with a **60s hard timeout** so a locked Firefox profile cannot freeze the queue. Same two clicks as the fail-pause modal, without the modal when it works: **Import from Firefox / browser** (Firefox then Edge, process tree killed on timeout) → file-only Netscape validate (no live `extract_info`) → **Retry this job**. Status lines: `Importing cookies from Firefox…`, `Cookies validated — waiting before retry…`, `Retrying download…`. Human fail-pause if import times out/fails or the retry still fails. An existing `cookies/<domain>.txt` is **not** a reason to re-run Firefox on every `unknown`. `auto_cookie_recovery` OFF skips this path entirely.

On `auth_required` / `bot_check` / `rate_limited` / `impersonation_missing`, or `unknown` with auth-like stderr, an Auto-impersonate host, or impersonate already in `tried`. Edge is the Firefox fallback. **Chrome App-Bound Encryption is not auto-fixed.**

Settings: **Auto cookie recovery (all sites)** (default ON), **Retry backoff (seconds)** (default 5, 0–60), and jitter (default 2, 0–15). Backoff is not applied to the first attempt, user Retry, or Skip.

This still does **not** open a browser window or an in-app WebView. It uses:

`yt-dlp --cookies-from-browser firefox --cookies <FrameForge cookies path> --skip-download <url>`

**Manual path:** Authenticate or the fail-pause **Import from Firefox / browser** button (same importer). Firefox is the default.

1. Click **Authenticate site…** (or **Import from Firefox / browser** on a bot/login pause).
2. Enter the site URL or domain.
3. **Firefox is the default.** Click **Import from Firefox**, or **Choose cookies.txt file**.
4. FrameForge runs the same `--cookies-from-browser` command as the auto path.
5. The Netscape file is validated (must contain at least one cookie row). Header-only stubs are rejected.
6. On success, later downloads for that domain use `resolve_cookiefile_for_url` automatically. YouTube then still uses the Innertube client list (`tv_downgraded`, etc.). See [YOUTUBE_CLIENTS.md](YOUTUBE_CLIENTS.md).

**Browser order** when auto-trying: `firefox`, then `edge`. Manual Authenticate may also offer Chrome/Brave, but Chrome ABE usually fails.

### Chrome App-Bound Encryption (honest limit)

Chrome cookie import **cannot be fixed by FrameForge**. Modern Chrome uses **App-Bound Encryption (DPAPI)**. Closing Chrome does not unlock those cookies. Prefer:

- Firefox Import, **or**
- Export a Netscape `cookies.txt` (extension such as “Get cookies.txt LOCALLY”) and import the file.

Edge/Brave may hit the same Chromium lock. ChromeCookieUnlock-style recovery is **not** bundled.

## Manual Netscape import (fallback)

1. Click **Authenticate site…**
2. Enter a URL or domain.
3. If cookies already exist for that domain, browser open is skipped (smart skip). Import again to replace.
4. Otherwise **Open browser**, log in / accept gates in your browser.
5. Export a Netscape `cookies.txt` (browser extension such as “Get cookies.txt LOCALLY”).
6. **Import cookies.txt** — validated as non-empty Netscape (tab-separated cookie rows). Empty/garbage files are rejected.

Header-only stubs created when opening the browser are **not** treated as usable cookies.

If a download fails with a login/bot/age/members wall on **any site**, FrameForge first tries **silent Firefox recovery** for that domain. If that is exhausted, the error panel / fail-pause modal offers:

- **Import from browser…** (prefilled URL)
- **Authenticate this site…** (manual cookies.txt)

Both remain available when auto recovery cannot finish the job.

## Notes

- Cookie files are never committed to git.
- Downloads still run sequentially and only after **Download selected** / **Download all pending**.

## PornHub / age gate

PornHub is one consumer of the same universal cookie path. Site file: `cookies\pornhub.com.txt` (from `https://www.pornhub.com/…`).

1. Open the URL in a browser, **accept the age gate**, sign in if needed (Firefox preferred).
2. FrameForge will try **silent Firefox import + backoff + retry** on the next auth-like failure (zero clicks when cookies are exportable).
3. If that path cannot finish, import from the fail-pause modal or write `pornhub.com.txt` yourself, then retry. `--impersonate chrome` is still required (see [ADULT_SITES.md](ADULT_SITES.md)). Cookies alone do not fix job-70-style HTTP 410 after impersonate+cookies.

Chrome App-Bound Encryption still applies: prefer Firefox or a cookies.txt export.
