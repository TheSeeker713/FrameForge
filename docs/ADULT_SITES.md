# Adult sites (PornHub / MindGeek)

Proven on this machine **2026-08-16**:

- yt-dlp **2026.07.04**
- `curl_cffi==0.13.0` → impersonate targets available (Chrome/Edge Windows included)
- `curl_cffi==0.16.0` → **unsupported** with this yt-dlp: Request Handlers omit curl_cffi; all impersonate targets unavailable

Working CLI (skip-download):

```powershell
python -m yt_dlp -v --impersonate chrome --cookies $env:USERPROFILE\Downloads\FrameForge\cookies\pornhub.com.txt --skip-download "https://www.pornhub.com/view_video.php?viewkey=6a5f2e146fdb9"
```

That extracted the page + m3u8 and format `hls-2313`. FrameForge job 70 failed because the app did not pass `--impersonate`, classified the HTTP 410 as **unknown**, and printed “no impersonate target”.

## What FrameForge does (v0.6.8)

1. Pins **`curl_cffi==0.13.0`**. Do **not** upgrade curl_cffi alone to 0.16.x unless yt-dlp is past ~2026.08.16.
2. When impersonate targets exist, PornHub / PornHubPremium / YouPorn / RedTube / Tube8 argv includes `--impersonate chrome` (or `edge` if Chrome is missing).
3. Settings → **Browser impersonate**: **Auto** (default, those hosts only) / **Always** / **Off**.
4. Auto/Always never start a PornHub download without impersonate when targets exist. If targets are missing, the job fails as `impersonation_missing` instead of a mystery 410.
5. `--check-env` JSON includes `impersonation`: yt-dlp version, curl_cffi version, `curl_cffi_supported`, `chrome_available`, `clients`, or `error` when Chrome is unavailable. Overall `ok` is false until Chrome is available.

## Cookies / age gate

Keep the site cookie file:

`%USERPROFILE%\Downloads\FrameForge\cookies\pornhub.com.txt`

1. Open the video in a browser, **accept the age gate**, and stay logged in if the site requires it.
2. Re-export Netscape cookies (Firefox import or cookies.txt) into that file.
3. Retry the job. FrameForge still passes `--impersonate chrome`.

Fail-pause for `impersonation_missing` and age/login (`auth_required`) offers Import from browser / cookies.txt, then retry. See [COOKIES.md](COOKIES.md) and [FAIL_PAUSE.md](FAIL_PAUSE.md).

## Error categories

| Signal | Category |
|--------|----------|
| no impersonate target / unsupported curl_cffi / Impersonate target not available | `impersonation_missing` |
| HTTP 410 + PornHub webpage **without** `--impersonate` in argv | `impersonation_missing` |
| HTTP 410 + `--impersonate` **without** `--cookies` | `auth_required` (age gate / cookies) |
| HTTP 410 **after** working impersonate **and** cookies | `not_available` |

Job-70-style stderr is **not** `unknown`.

## Honest limit

A video that is **truly deleted** still returns **HTTP 410 in a browser**. FrameForge then reports `not_available` and tells you to confirm in a browser — it cannot download a gone page.

## Manual checklist (not CI)

CI must **not** download live PornHub. After cookies + impersonate on this machine:

1. `python -m frameforge --check-env` → `impersonation.ok` / Chrome available.
2. Enqueue a **browser-viewable** PH URL (the viewkey above only if it still plays in a browser).
3. Job argv includes `--impersonate chrome` and `--cookies …\pornhub.com.txt` when that file is valid Netscape.
4. Job completes, or fails `not_available` only if the browser also shows gone.

See [TESTING.md](TESTING.md) and [YTDLP_PARITY.md](YTDLP_PARITY.md).
