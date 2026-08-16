"""Structured job error categories for GUI hints and persistence."""

from __future__ import annotations

import re
from typing import Any

from frameforge.download.auth_hints import (
    auth_action_hint,
    is_auth_failure,
    normalize_domain_safe,
)

AUTH_REQUIRED = "auth_required"
BOT_CHECK = "bot_check"
RATE_LIMITED = "rate_limited"
NOT_AVAILABLE = "not_available"
NETWORK = "network"
FFMPEG = "ffmpeg"
ARIA2_FORBIDDEN = "aria2_forbidden"
BLOCKED_4K = "blocked_4k"
CANCELLED = "cancelled"
JS_RUNTIME = "js_runtime"
IMPERSONATION_MISSING = "impersonation_missing"
OUTPUT_MISSING = "output_missing"
DISK_SPACE = "disk_space"
UPSCALE_LIMIT = "upscale_limit"
DB_ERROR = "db_error"
UNKNOWN = "unknown"

CATEGORIES = (
    AUTH_REQUIRED,
    BOT_CHECK,
    RATE_LIMITED,
    NOT_AVAILABLE,
    NETWORK,
    FFMPEG,
    ARIA2_FORBIDDEN,
    BLOCKED_4K,
    CANCELLED,
    JS_RUNTIME,
    IMPERSONATION_MISSING,
    OUTPUT_MISSING,
    DISK_SPACE,
    UPSCALE_LIMIT,
    DB_ERROR,
    UNKNOWN,
)

# Failures that should pause a bulk run (bot/auth, missing EJS, missing output, disk, hard unknown).
FAIL_PAUSE_CATEGORIES = frozenset(
    {
        AUTH_REQUIRED,
        BOT_CHECK,
        JS_RUNTIME,
        IMPERSONATION_MISSING,
        OUTPUT_MISSING,
        DISK_SPACE,
        UPSCALE_LIMIT,
        UNKNOWN,
    }
)
STDERR_TAIL_LINES = 12
STDERR_TAIL_CHARS = 2000

_BOT_RE = re.compile(
    r"sign in to confirm"
    r"|you.?re not a bot"
    r"|you are not a bot"
    r"|not a bot"
    r"|bot.?check"
    r"|bot detection"
    r"|recaptcha"
    r"|hcaptcha"
    r"|unusual traffic"
    r"|confirm you.?re (a )?human"
    r"|verify you are (a )?human"
    r"|please complete the security check"
    r"|automated (queries|traffic|access|requests)"
    r"|detected unusual",
    re.IGNORECASE,
)
_RATE_RE = re.compile(
    r"http error 429"
    r"|status code 429"
    r"|too many requests"
    r"|rate[- ]limit"
    r"|slow down"
    r"|429 too many",
    re.IGNORECASE,
)
_UNAVAIL_RE = re.compile(
    r"video unavailable"
    r"|this video is (private|unavailable)"
    r"|private video"
    r"|has been (removed|deleted)"
    r"|copyright"
    r"|not (currently )?available"
    r"|http error 404"
    r"|status code 404"
    r"|cancelled by the uploader"
    r"|this live event was cancelled"
    r"|live event (has been |was )?cancelled",
    re.IGNORECASE,
)
_NETWORK_RE = re.compile(
    r"connection (reset|refused|aborted|timed? ?out)"
    r"|timed? ?out"
    r"|name or service not known"
    r"|getaddrinfo"
    r"|failed to resolve"
    r"|temporary failure in name resolution"
    r"|network is unreachable"
    r"|ssl(eof|error)?"
    r"|http error 50[234]"
    r"|errno \d+"
    r"|urlopen error",
    re.IGNORECASE,
)
_FFMPEG_RE = re.compile(
    r"(?<!-)\bffmpeg\b|\bffprobe\b|\blibx264\b|\baac\b encoder",
    re.IGNORECASE,
)
_ARIA2_FORBIDDEN_RE = re.compile(
    r"aria2c exited with code 22"
    r"|aria2c.*\bcode 22\b"
    r"|\[#\w+\s+.*status[=:\s]*403"
    r"|googlevideo\.com.*\b403\b"
    r"|\b403\b.*googlevideo"
    r"|http error 403.*aria2"
    r"|aria2.*http error 403",
    re.IGNORECASE,
)
_BLOCKED_4K_RE = re.compile(r"blocked:.*(?:4k|2160)|height\s*=\s*2[1-9]\d{2}", re.IGNORECASE)
_JS_RUNTIME_RE = re.compile(
    r"n challenge solving failed"
    r"|signature solving failed"
    r"|only images are available"
    r"|challenge solver script"
    r"|yt-dlp/ejs"
    r"|yt-dlp-ejs"
    r"|github\.com/yt-dlp/yt-dlp/wiki/ejs"
    r"|no js runtime"
    r"|js runtime",
    re.IGNORECASE,
)
_IMPERSONATE_MISSING_RE = re.compile(
    r"impersonate target.{0,80}not available"
    r"|no impersonate target"
    r"|unsupported impersonate"
    r"|unsupported curl_cffi"
    r"|curl_cffi is not available"
    r"|curl_cffi.*(unsupported|not installed)"
    r"|install curl_cffi"
    r"|without curl_cffi"
    r"|impersonated requests, but no impersonate",
    re.IGNORECASE,
)
_HTTP_410_RE = re.compile(
    r"http error 410"
    r"|status code 410"
    r"|\b410 gone\b"
    r"|410: gone",
    re.IGNORECASE,
)


def is_aria2_forbidden(message: str | None) -> bool:
    """True for aria2c exit 22 / googlevideo HTTP 403 (CDN block, not FFmpeg)."""
    text = str(message or "")
    if not text.strip():
        return False
    if _ARIA2_FORBIDDEN_RE.search(text):
        return True
    lower = text.lower()
    if "aria2" in lower and ("403" in lower or "exited with code 22" in lower):
        return True
    return False


def _argv_has_flag(text: str, flag: str) -> bool:
    return bool(re.search(rf"(?:^|[\s\"']){re.escape(flag)}(?:[\s\"'=]|$)", text, re.IGNORECASE))


def classify_error(message: str | None, *, status: str | None = None, url: str | None = None) -> str:
    """Map a human error string (and optional status) to a stable category."""
    if status == "cancelled":
        return CANCELLED
    text = str(message or "")
    lower = text.lower()
    if _JS_RUNTIME_RE.search(text) or (
        "requested format" in lower and "not available" in lower and "image" in lower
    ):
        return JS_RUNTIME
    if _IMPERSONATE_MISSING_RE.search(text):
        return IMPERSONATION_MISSING
    if _HTTP_410_RE.search(text):
        from frameforge.download.impersonate import adult_site_in_text, url_needs_impersonate

        adult = adult_site_in_text(text) or bool(url and url_needs_impersonate(url))
        used_impersonate = _argv_has_flag(text, "--impersonate")
        used_cookies = _argv_has_flag(text, "--cookies")
        if adult and not used_impersonate:
            return IMPERSONATION_MISSING
        if adult and used_impersonate and not used_cookies:
            return AUTH_REQUIRED
        return NOT_AVAILABLE
    if is_aria2_forbidden(text):
        return ARIA2_FORBIDDEN
    if (
        "downloaded file not found" in lower
        or "archive lists this video" in lower
        or "file is missing on disk" in lower
    ):
        return OUTPUT_MISSING
    if "not enough disk space" in lower or "disk space for upscale" in lower:
        return DISK_SPACE
    if "upscale refused" in lower and "max allowed" in lower:
        return UPSCALE_LIMIT
    if (
        "cannot start a transaction" in lower
        or "cannot commit transaction" in lower
        or "no transaction is active" in lower
        or "database is locked" in lower
        or "database is busy" in lower
        or "sqlite3.operationalerror" in lower
        or ("operationalerror" in lower and "sqlite" in lower)
    ):
        return DB_ERROR
    if _BOT_RE.search(text):
        return BOT_CHECK
    if _RATE_RE.search(text):
        return RATE_LIMITED
    if _UNAVAIL_RE.search(text):
        return NOT_AVAILABLE
    if is_auth_failure(text):
        return AUTH_REQUIRED
    if _BLOCKED_4K_RE.search(text) or ("blocked" in lower and "2160" in lower):
        return BLOCKED_4K
    # argv often includes --ffmpeg-location C:\ffmpeg\bin — that is not an FFmpeg failure.
    ffmpeg_text = re.sub(r"\nargv:.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    if _FFMPEG_RE.search(ffmpeg_text):
        return FFMPEG
    if _NETWORK_RE.search(text):
        return NETWORK
    return UNKNOWN


def stderr_tail(message: str | None, *, max_lines: int = STDERR_TAIL_LINES) -> str:
    """Last non-empty lines of yt-dlp/ffmpeg output for the error panel."""
    lines = [ln.strip() for ln in str(message or "").splitlines() if ln.strip()]
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > STDERR_TAIL_CHARS:
        return tail[-STDERR_TAIL_CHARS:]
    return tail


def format_ytdlp_exit_error(
    rc: int,
    lines: list[str] | tuple[str, ...],
    *,
    max_lines: int = STDERR_TAIL_LINES,
    argv: list[str] | None = None,
) -> str:
    """Combine exit code with a stderr/stdout tail so classifiers see bot/auth text."""
    tail = stderr_tail("\n".join(lines), max_lines=max_lines)
    if tail:
        msg = f"yt-dlp exited with code {rc}\n{tail}"
    else:
        msg = f"yt-dlp exited with code {rc}\nno stderr; see invocation log"
    if argv:
        from frameforge.download.invocation import argv_summary

        summary = argv_summary(list(argv))
        if summary:
            msg += f"\nargv: {summary}"
    return msg


def human_cause(category: str) -> str:
    return {
        AUTH_REQUIRED: "This site wants you signed in (cookies or login).",
        BOT_CHECK: "The site thinks this is automated traffic (bot check).",
        RATE_LIMITED: "The site is rate-limiting requests (HTTP 429 / slow down).",
        NOT_AVAILABLE: (
            "The video is private, removed, or otherwise unavailable. "
            "If a browser also shows HTTP 410 / gone, it is truly deleted."
        ),
        NETWORK: "A network error interrupted the download.",
        FFMPEG: "FFmpeg/ffprobe failed while processing the file.",
        ARIA2_FORBIDDEN: "Fast downloader (aria2) was blocked by the CDN (HTTP 403).",
        BLOCKED_4K: "This source is 4K/≥2160p and cannot be upscaled here.",
        CANCELLED: "The job was cancelled.",
        JS_RUNTIME: (
            "YouTube needs Deno (or Node) plus yt-dlp-ejs to solve n/signature challenges."
        ),
        IMPERSONATION_MISSING: (
            "This site needs browser impersonation (curl_cffi + --impersonate chrome). "
            "Run python -m frameforge --check-env."
        ),
        OUTPUT_MISSING: "The download finished but the video file is missing on disk.",
        DISK_SPACE: "This upscale needs more free disk space for temporary PNG frames.",
        UPSCALE_LIMIT: "This clip is longer than the PNG-pipeline duration cap (streaming is not shipped yet).",
        DB_ERROR: "The local queue database hit a lock or transaction error (not a yt-dlp failure).",
        UNKNOWN: "The download failed for an unclassified reason.",
    }.get(category, "The download failed.")


def suggested_actions(category: str) -> list[str]:
    if category in (AUTH_REQUIRED, BOT_CHECK):
        return [
            "Import from browser (Firefox preferred)",
            "Authenticate site / Import cookies.txt",
            "Retry this job",
        ]
    if category == RATE_LIMITED:
        return [
            "Wait a few minutes, then retry",
            "Import cookies if the site is logged-in only",
            "Enable gentle rate mode in Settings after resume",
        ]
    if category == NETWORK:
        return ["Check the network connection", "Retry this job"]
    if category == FFMPEG:
        return ["Confirm FFmpeg is on PATH (`python -m frameforge --check-env`)", "Retry"]
    if category == ARIA2_FORBIDDEN:
        return ["Retry this job (built-in downloader)", "Check cookies if it still fails"]
    if category == BLOCKED_4K:
        return ["Select a lower-resolution source (≤1080p)"]
    if category == CANCELLED:
        return ["Re-download or Download selected if you still want this item"]
    if category == JS_RUNTIME:
        return [
            "Install Deno and restart FrameForge",
            'pip install -U "yt-dlp[default]" yt-dlp-ejs',
            "Retry this job",
        ]
    if category == IMPERSONATION_MISSING:
        return [
            "Run python -m frameforge --check-env (Chrome impersonate must be available)",
            "pip install curl_cffi==0.13.0 (do not upgrade to 0.16 with yt-dlp 2026.07.04)",
            "Accept the age gate in a browser, import cookies, then retry with impersonate",
        ]
    if category == NOT_AVAILABLE:
        return [
            "Confirm the URL in a browser — truly deleted videos still return HTTP 410",
            "Skip this job — it cannot be downloaded",
        ]
    if category == OUTPUT_MISSING:
        return [
            "Retry this job (force re-download if the archive is stale)",
            "Open the download folder",
            "Skip & resume queue",
        ]
    if category == DISK_SPACE:
        return [
            "Free disk space on the FrameForge temp drive",
            "Retry this job",
            "Skip & resume queue",
        ]
    if category == UPSCALE_LIMIT:
        return [
            "Raise max upscale duration in Settings (PNG pipeline still uses huge temp)",
            "Skip this clip until streaming upscale ships",
        ]
    if category == DB_ERROR:
        return ["Retry this job", "Restart FrameForge if the queue stays stuck"]
    return ["Retry failed", "Inspect the error message"]


def suggested_action(category: str, *, auth_hint: str | None = None) -> str | None:
    if category in (AUTH_REQUIRED, BOT_CHECK, IMPERSONATION_MISSING) and auth_hint:
        return auth_hint
    actions = suggested_actions(category)
    if not actions:
        return None
    return "Next: " + "; ".join(actions) + "."


def should_fail_pause(category: str | None) -> bool:
    return category in FAIL_PAUSE_CATEGORIES


def format_error_panel(job: Any | None) -> str:
    """Category + human cause + message + suggested next actions."""
    if job is None:
        return ""
    err = getattr(job, "error", None)
    status = getattr(job, "status", None)
    opts = job.options() if hasattr(job, "options") else {}
    cat = opts.get("error_category")
    if status == "paused":
        return "Paused. Resume when you want this download to continue."
    if not cat:
        cat = classify_error(err, status=status, url=getattr(job, "url", None)) if (err or status == "cancelled") else None
    if not err and status != "cancelled":
        return ""
    lines: list[str] = []
    if cat:
        lines.append(f"Category: {cat}")
        lines.append(f"Cause: {opts.get('error_cause') or human_cause(cat)}")
    if err:
        lines.append(str(err))
    elif status == "cancelled":
        lines.append("Cancelled by user.")
    hint = opts.get("auth_hint") if cat in (AUTH_REQUIRED, BOT_CHECK, IMPERSONATION_MISSING) else None
    action = suggested_action(cat or UNKNOWN, auth_hint=hint)
    if action and action not in "\n".join(lines):
        lines.append("")
        lines.append(action)
    stored = opts.get("error_actions")
    if isinstance(stored, list) and stored:
        extra = "Actions: " + " / ".join(str(a) for a in stored)
        if extra not in "\n".join(lines):
            lines.append(extra)
    return "\n".join(lines)


def annotate_job_error(
    repo: Any,
    job_id: int,
    message: str,
    *,
    status: str = "failed",
    url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Persist human error + error_category (and auth hint when applicable)."""
    job = repo.get(job_id)
    url = url or job.url
    cat = classify_error(message, status=status, url=url)
    patch: dict[str, Any] = {
        "error_category": cat,
        "error_cause": human_cause(cat) or "The download failed.",
        "error_actions": suggested_actions(cat),
        "error_stderr_tail": stderr_tail(message),
    }
    if extra:
        patch.update(extra)
    if cat in (AUTH_REQUIRED, BOT_CHECK, IMPERSONATION_MISSING):
        patch["auth_required"] = True
        patch["auth_hint"] = auth_action_hint(url)
        patch["auth_domain"] = normalize_domain_safe(url)
    else:
        patch["auth_required"] = False
    if cat == OUTPUT_MISSING:
        archive_hit = "archive lists this video" in str(message or "").lower() or bool(
            (job.options() if hasattr(job, "options") else {}).get("archive_hit")
        )
        if archive_hit:
            patch["archive_hit"] = True
            patch["force_redownload"] = True
    return repo.update_status(job_id, status, error=str(message), options_patch=patch)


def option_patch_from_exc(exc: BaseException) -> dict[str, Any]:
    patch = getattr(exc, "option_patch", None)
    if callable(patch):
        data = patch()
        return data if isinstance(data, dict) else {}
    if isinstance(patch, dict):
        return dict(patch)
    return {}
