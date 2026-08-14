"""Offline stderr snippets for error classification (no network)."""

from __future__ import annotations

from frameforge.errors import AUTH_REQUIRED, BOT_CHECK, NETWORK, NOT_AVAILABLE, RATE_LIMITED, UNKNOWN

# (category, blob) — blobs mimic yt-dlp stdout+stderr tails.
CORPUS: list[tuple[str, str]] = [
    (
        BOT_CHECK,
        "[youtube] abc: Downloading webpage\nERROR: [youtube] abc: Sign in to confirm you’re not a bot",
    ),
    (
        BOT_CHECK,
        "ERROR: Sign in to confirm you are not a bot. Use --cookies-from-browser.",
    ),
    (
        BOT_CHECK,
        "WARNING: [youtube] unusual traffic detected\nERROR: Please complete the security check (recaptcha)",
    ),
    (
        BOT_CHECK,
        "ERROR: Please verify you are a human before continuing",
    ),
    (
        AUTH_REQUIRED,
        "ERROR: login required to download this video",
    ),
    (
        AUTH_REQUIRED,
        "ERROR: Confirm your age to continue. This video is age-restricted.",
    ),
    (
        AUTH_REQUIRED,
        "HTTP Error 403: Forbidden\nUse --cookies or --cookies-from-browser",
    ),
    (
        RATE_LIMITED,
        "ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests",
    ),
    (
        NOT_AVAILABLE,
        "ERROR: [youtube] Video unavailable. This video is private.",
    ),
    (
        NETWORK,
        "ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>",
    ),
    (
        UNKNOWN,
        "yt-dlp exited with code 1",
    ),
]
