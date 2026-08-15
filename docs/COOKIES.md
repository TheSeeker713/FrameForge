# Cookies / authentication

FrameForge stores per-domain Netscape cookie files under:

`%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt`

Authenticate and Settings show that resolved folder and list domain `*.txt` files found. **Open cookies folder** launches Explorer on that directory only (no theme or DWM changes).

## Import from browser (v0.5.6)

User-triggered only — FrameForge never auto-opens a browser loop.

1. Click **Authenticate site…** (or **Import from Firefox / browser** on a bot/login pause).
2. Enter the site URL or domain.
3. **Firefox is the default.** Click **Import from Firefox**, or **Choose cookies.txt file**.
4. FrameForge runs:

   `yt-dlp --cookies-from-browser <browser> --cookies <FrameForge cookies path> --skip-download <url>`

5. The Netscape file is validated (must contain at least one cookie row). Header-only stubs are rejected.
6. On success, later downloads for that domain use `resolve_cookiefile_for_url` automatically. YouTube then still uses the Innertube client list (`tv_downgraded`, etc.). See [YOUTUBE_CLIENTS.md](YOUTUBE_CLIENTS.md).

**Browser order** when auto-trying: `firefox`, then `edge`, `chrome`, `brave`.

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

If a download fails with a login/bot/age/members wall, the error panel offers:

- **Import from browser…** (prefilled URL)
- **Authenticate this site…** (manual cookies.txt)

Both are user-triggered.

## Notes

- Cookie files are never committed to git.
- Downloads still run sequentially and only after **Download selected** / **Download all pending**.
