"""Per-job rate cap, fragment concurrency, and inter-job cooldown (defaults: fast job, 3s gap)."""

from __future__ import annotations

from typing import Any

INTER_JOB_DELAY_SETTING = "inter_job_delay_sec"
MAX_DOWNLOAD_RATE_SETTING = "max_download_rate"
CONCURRENT_FRAGMENTS_SETTING = "concurrent_fragments"
ARIA2_CONNECTIONS_SETTING = "aria2_connections"
DEFAULT_INTER_JOB_DELAY_SEC = 3.0
MAX_INTER_JOB_DELAY_SEC = 60.0
DEFAULT_CONCURRENT_FRAGMENTS = 8
MIN_CONCURRENT_FRAGMENTS = 1
MAX_CONCURRENT_FRAGMENTS = 32
DEFAULT_ARIA2_CONNECTIONS = 16
MIN_ARIA2_CONNECTIONS = 1
MAX_ARIA2_CONNECTIONS = 16
DEFAULT_THROTTLED_RATE = "100K"
DEFAULT_HTTP_CHUNK_SIZE = "10M"
ARIA2_PIECE_SIZE = "1M"
ARIA2_EXTRA_FLAGS = (
    "--file-allocation=none",
    "--summary-interval=1",
    "--enable-color=false",
    "-c",
    "--allow-overwrite=true",
    "--auto-file-renaming=false",
)


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


def _int_setting(
    repo: Any | None,
    key: str,
    default: int,
    *,
    lo: int,
    hi: int,
) -> int:
    raw = str(default)
    if repo is not None and hasattr(repo, "get_setting"):
        raw = str(repo.get_setting(key, str(default)) or default)
    try:
        value = int(float(str(raw).strip()))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def concurrent_fragments(repo: Any | None = None) -> int:
    """yt-dlp -N / --concurrent-fragments. Default 8 (never 1 unless Settings says so)."""
    return _int_setting(
        repo,
        CONCURRENT_FRAGMENTS_SETTING,
        DEFAULT_CONCURRENT_FRAGMENTS,
        lo=MIN_CONCURRENT_FRAGMENTS,
        hi=MAX_CONCURRENT_FRAGMENTS,
    )


def aria2_connections(repo: Any | None = None) -> int:
    """aria2c -x / -s. Default 16 (aria2 max)."""
    return _int_setting(
        repo,
        ARIA2_CONNECTIONS_SETTING,
        DEFAULT_ARIA2_CONNECTIONS,
        lo=MIN_ARIA2_CONNECTIONS,
        hi=MAX_ARIA2_CONNECTIONS,
    )


def throttled_rate_bps() -> int:
    return parse_rate_bps(DEFAULT_THROTTLED_RATE) or 100 * 1024


def http_chunk_size_bytes() -> int:
    return parse_rate_bps(DEFAULT_HTTP_CHUNK_SIZE) or 10 * 1024 * 1024


def aria2c_opt_args(connections: int | None = None) -> list[str]:
    n = str(connections if connections is not None else DEFAULT_ARIA2_CONNECTIONS)
    return ["-x", n, "-s", n, "-k", ARIA2_PIECE_SIZE, *ARIA2_EXTRA_FLAGS]


def aria2c_cli_args(connections: int | None = None) -> str:
    return " ".join(aria2c_opt_args(connections))
