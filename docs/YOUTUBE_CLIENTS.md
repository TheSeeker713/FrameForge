# YouTube Innertube player clients

FrameForge asks yt-dlp to try several YouTube **player clients** so most **public** videos download without a cookie ritual.

Default extractor arg:

```
youtube:player_client=android_vr,tv_downgraded,web_embedded,web_safari
```

Settings: **YouTube Innertube clients** (on by default). Turn on **Use yt-dlp default YouTube clients** to omit `--extractor-args`. You can edit the client order.

## What each client is

| Client | Typical role |
|--------|----------------|
| `android_vr` | Logged-out Innertube client that often still returns real formats. |
| `tv_downgraded` | TV client; useful logged-out and after cookies. |
| `web_embedded` | Embedded web player; lighter than full `web`. |
| `web_safari` | Safari-flavored web client; another public path. |

yt-dlp tries them in order until formats resolve. FrameForge still uses `-f bv*+ba/b` (or the job’s format preset).

## PO token

Some web clients require a **PO token**. FrameForge does not mint PO tokens. If a client needs one, yt-dlp skips it or fails that client and continues the list. Deno + `yt-dlp-ejs` still matter for n/signature challenges on clients that use them.

## When cookies are still required

Innertube rotation does **not** replace login for:

- Age-gated videos
- Members-only / paid content
- Accounts that YouTube has put behind a bot wall (“confirm you’re not a bot”)

Then use **Firefox import** or a Netscape **cookies.txt**. Chrome App-Bound Encryption often cannot be decrypted on modern Windows — FrameForge will not pretend otherwise. See [COOKIES.md](COOKIES.md) and [SHELL_SAFETY.md](SHELL_SAFETY.md) (unrelated to cookies; chrome HWND rules).

After valid cookies, the same client list still applies; `tv_downgraded` is the usual authed workhorse.
