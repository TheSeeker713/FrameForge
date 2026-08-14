# Bot-check playbook

FrameForge does not bypass YouTube (or other) bot walls. It **pauses** so a bulk list is not burned, **imports cookies the user obtained in a real browser**, **validates** those cookies, then **retries once on explicit action**.

## User journey

1. A download fails with “Sign in to confirm you’re not a bot” (or login / age / 403).
2. The worker **disarms**. Remaining jobs stay **pending**. Fail-pause UI shows the human cause.
3. **Import from Firefox** (preferred) or **Authenticate** → cookies.txt. Files land in `%USERPROFILE%\Downloads\FrameForge\cookies\<domain>.txt` (Netscape).
4. FrameForge **validates** before resume:
   - File is non-empty Netscape.
   - Optional dry `extract_info` probe for that URL (injectable in tests; real yt-dlp in the app).
   - If this domain was already validated in the **current session**, the probe is skipped.
5. On success: “Cookies look valid… **Retry this job and resume the queue**.” The next few jobs use a **gentle rate** cooldown (sleep + 2 MiB/s) without permanently turning on Settings → Gentle rate.
6. On failure: the modal **stays open** with “Cookies did not unlock this site — try browser login then import again.”
7. Retry that fails again hits the **same** fail-pause entrypoint. No silent loop.

## Engineering guarantees

| Guarantee | Where |
|-----------|--------|
| stderr tail is classified (`bot_check` / `auth_required` / `rate_limited` / …) with non-empty `error_cause` | `frameforge.errors` |
| Fail-pause on bot/auth/unknown while armed | `maybe_fail_pause` |
| Validate before resume | `frameforge.download.cookie_validate` |
| Import never arms the worker | `UiBridge.recover_bot_cookies` |
| Gentle cooldown is N jobs, not a surprise permanent cap | `gentle_jobs_left` setting |

## Honest limits

Some sites require an interactive login in a **real browser** first (Firefox recommended). Chromium cookies may be locked or App-Bound Encrypted. FrameForge’s job is to import, store, apply, and pause until that works — not to hammer the CDN.
