"""Per-job rate cap and inter-job cooldown (defaults: fast job, 3s gap)."""

from __future__ import annotations

from typing import Any

INTER_JOB_DELAY_SETTING = "inter_job_delay_sec"
MAX_DOWNLOAD_RATE_SETTING = "max_download_rate"
DEFAULT_INTER_JOB_DELAY_SEC = 3.0
MAX_INTER_JOB_DELAY_SEC = 60.0


def inter_job_delay_sec(repo: Any | None = None) -> float:
    raw = "3"
    if repo is not None and hasattr(repo, "get_setting"):
        raw = str(repo.get_setting(INTER_JOB_DELAY_SETTING, "3") or "3")
    try:
        value = float(raw.strip())
    except ValueError:
        value = DEFAULT_INTER_JOB_DELAY_SEC
    return max(0.0, min(MAX_INTER_JOB_DELAY_SEC, value))


def parse_rate_bps(raw: str | None) -> int | None:
    """Parse Settings rate: 0/empty = unlimited; 50K / 2M / integer bytes."""
    text = str(raw or "").strip().lower().replace(" ", "")
    if not text or text in {"0", "off", "unlimited", "none"}:
        return None
    mult = 1.0
    if text.endswith(("kib/s", "kib", "kb/s", "kb")):
        mult = 1024.0
        text = text.split("k", 1)[0]
    elif text.endswith(("mib/s", "mib", "mb/s", "mb")):
        mult = 1024.0**2
        text = text.split("m", 1)[0]
    elif text.endswith(("gib/s", "gib", "gb/s", "gb")):
        mult = 1024.0**3
        text = text.split("g", 1)[0]
    elif text.endswith("k"):
        mult = 1024.0
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1024.0**2
        text = text[:-1]
    elif text.endswith("g"):
        mult = 1024.0**3
        text = text[:-1]
    elif text.endswith("b"):
        text = text[:-1]
    try:
        value = float(text)
    except ValueError:
        return None
    bps = int(value * mult)
    return bps if bps > 0 else None


def max_download_rate_bps(repo: Any | None = None) -> int | None:
    if repo is None or not hasattr(repo, "get_setting"):
        return None
    return parse_rate_bps(str(repo.get_setting(MAX_DOWNLOAD_RATE_SETTING, "0") or "0"))
