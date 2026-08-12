# Cookies / authentication (Tier 1.4)

FrameForge stores per-domain Netscape cookie files under:

`%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt`

## Authenticate flow (GUI)

1. Click **Authenticate site…**
2. Enter a URL or domain.
3. If cookies already exist for that domain, browser open is skipped (smart skip). Import again to replace.
4. Otherwise **Open browser**, log in / accept gates in your browser.
5. Export a Netscape `cookies.txt` (browser extension such as “Get cookies.txt LOCALLY”).
6. **Import cookies.txt** — validated as non-empty Netscape (tab-separated cookie rows). Empty/garbage files are rejected. Saved under the cookies folder.
7. Subsequent yt-dlp downloads for that domain automatically pass `cookiefile`.

Header-only stubs created when opening the browser are **not** treated as usable cookies (smart skip requires a real cookie row).

If a download fails with a login/bot/age/members wall, the error panel offers **Authenticate this site…** prefilled with that job’s URL (user-triggered; no auto-open loop).

## Notes

- Cookie files are never committed to git.
- Downloads still run sequentially and only after **Download selected** / **Download all pending**.
