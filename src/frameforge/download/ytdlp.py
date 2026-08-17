"""yt-dlp based downloader with aria2c, resume, archive, and rich progress."""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

log = logging.getLogger("frameforge.download.ytdlp")

from frameforge.paths import archive_dir, downloads_dir, ensure_output_tree
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused, popen_creationflags

if TYPE_CHECKING:
    from frameforge.queue.process_registry import ProcessRegistry


ProgressCb = Callable[[float, dict[str, Any]], None]

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_SIZE_PAIR_RE = re.compile(
    r"SIZE:\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)",
    re.IGNORECASE,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# yt-dlp: "at  512.00KiB/s"  aria2c: "DL:1.1MiB" / "DL:512KiB/s" / "SPD:512KiB/s"
_SPEED_RE = re.compile(
    r"(?:at\s+|DL:\s*|SPD:\s*)(\d+(?:\.\d+)?)\s*([KMGT]?i?B)(?:\s*/\s*s)?",
    re.IGNORECASE,
)
# yt-dlp: "ETA 00:19" / "ETA 1:05:00"  aria2c: "ETA:18s" / "ETA:1m18s"
_ETA_CLOCK_RE = re.compile(
    r"ETA[:\s]+(\d+):(\d{2})(?::(\d{2}))?",
    re.IGNORECASE,
)
_ETA_HMS_RE = re.compile(
    r"ETA[:\s]+(?:(\d+)\s*h)?(?:(\d+)\s*m)?(?:(\d+)\s*s)\b",
    re.IGNORECASE,
)

_UNIT_TO_BPS = {
    "B": 1.0,
    "KB": 1000.0,
    "MB": 1_000_000.0,
    "GB": 1_000_000_000.0,
    "TB": 1_000_000_000_000.0,
    "KIB": 1024.0,
    "MIB": 1024.0**2,
    "GIB": 1024.0**3,
    "TIB": 1024.0**4,
}


def _format_speed(bps: float | None) -> str:
    if bps is None or bps <= 0:
        return "—"
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    val = float(bps)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} GiB/s"


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _speed_to_bps(value: float, unit: str) -> float:
    key = unit.strip().upper()
    return value * _UNIT_TO_BPS.get(key, 1.0)


def _eta_seconds_from_line(line: str) -> float | None:
    if re.search(r"ETA[:\s]+unknown\b", line, re.IGNORECASE):
        return None
    clock = _ETA_CLOCK_RE.search(line)
    if clock:
        if clock.group(3) is not None:
            return float(
                int(clock.group(1)) * 3600
                + int(clock.group(2)) * 60
                + int(clock.group(3))
            )
        return float(int(clock.group(1)) * 60 + int(clock.group(2)))
    hms = _ETA_HMS_RE.search(line)
    if hms and any(hms.group(i) for i in (1, 2, 3)):
        hours = int(hms.group(1) or 0)
        minutes = int(hms.group(2) or 0)
        seconds = int(hms.group(3) or 0)
        return float(hours * 3600 + minutes * 60 + seconds)
    return None


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def iter_progress_lines(text: str) -> list[str]:
    """Split mixed CR/LF process output into individual progress-capable lines."""
    return [p for p in re.split(r"[\r\n]+", text) if p.strip()]


def iter_subprocess_text_chunks(stream: Any) -> Any:
    """Yield decoded lines from a binary stdout stream, splitting on CR and LF."""
    buf = b""
    while True:
        chunk = stream.read(256)
        if not chunk:
            if buf.strip():
                yield buf.decode("utf-8", errors="replace")
            break
        buf += chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode("utf-8")
        while True:
            idx_n = buf.find(b"\n")
            idx_r = buf.find(b"\r")
            if idx_n < 0 and idx_r < 0:
                break
            if idx_n < 0:
                idx = idx_r
            elif idx_r < 0:
                idx = idx_n
            else:
                idx = min(idx_n, idx_r)
            line, buf = buf[:idx], buf[idx + 1 :]
            if line.endswith(b"\r"):
                line = line[:-1]
            text = line.decode("utf-8", errors="replace")
            if text.strip():
                yield text


def parse_cli_progress_line(line: str) -> dict[str, Any] | None:
    """Parse a yt-dlp or aria2c stdout progress line into hook-compatible meta.

    Returns None when the line is not a progress update.
    """
    line = _strip_ansi(line or "")
    if not line:
        return None
    lower = line.lower()
    looks_progress = (
        "[download]" in lower
        or "eta" in lower
        or "dl:" in lower
        or "spd:" in lower
        or "size:" in lower
        or "/s" in lower
    )
    if not looks_progress:
        return None

    percent: float | None = None
    pct_m = _PCT_RE.search(line)
    if pct_m:
        percent = max(0.0, min(100.0, float(pct_m.group(1))))
    else:
        size_m = _SIZE_PAIR_RE.search(line)
        if size_m:
            cur = _speed_to_bps(float(size_m.group(1)), size_m.group(2))
            total = _speed_to_bps(float(size_m.group(3)), size_m.group(4))
            if total > 0:
                percent = max(0.0, min(100.0, 100.0 * cur / total))
    if percent is None:
        return None

    speed_bps: float | None = None
    speed_m = _SPEED_RE.search(line)
    if speed_m:
        speed_bps = _speed_to_bps(float(speed_m.group(1)), speed_m.group(2))
        if speed_bps <= 0:
            speed_bps = None
    eta_seconds = _eta_seconds_from_line(line)
    return {
        "percent": percent,
        "speed_bps": speed_bps,
        "eta_seconds": eta_seconds,
        "speed_str": _format_speed(speed_bps),
        "eta_str": _format_eta(eta_seconds),
    }


@dataclass
class DownloadResult:
    path: Path
    title: str
    info: dict[str, Any]


GENTLE_RATE_SETTING = "gentle_rate_mode"
GENTLE_SLEEP_INTERVAL = 2.0
GENTLE_MAX_SLEEP_INTERVAL = 5.0
GENTLE_LIMIT_RATE_BPS = 2 * 1024 * 1024  # 2 MiB/s — off by default


def apply_gentle_rate(downloader: "YtDlpDownloader", enabled: bool) -> None:
    if enabled:
        downloader.sleep_interval = GENTLE_SLEEP_INTERVAL
        downloader.max_sleep_interval = GENTLE_MAX_SLEEP_INTERVAL
        downloader.limit_rate_bps = GENTLE_LIMIT_RATE_BPS
    else:
        downloader.sleep_interval = None
        downloader.limit_rate_bps = None


class YtDlpDownloader:
    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        archive_file: Path | None = None,
        format_preference: str = "best",
        use_aria2c: bool = True,
        cookiefile: Path | None = None,
    ) -> None:
        ensure_output_tree()
        self.output_dir = output_dir or downloads_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.archive_file = archive_file or (archive_dir() / "ytdlp-archive.txt")
        self.archive_file.parent.mkdir(parents=True, exist_ok=True)
        self.format_preference = format_preference
        self.use_aria2c = use_aria2c
        self.cookiefile = cookiefile
        self.sleep_interval: float | None = None
        self.max_sleep_interval: float = 5.0
        self.limit_rate_bps: int | None = None
        self.last_invocation: dict[str, Any] | None = None
        self.youtube_innertube: bool = True
        self.youtube_player_clients: str | None = None
        self.concurrent_fragments: int | None = None
        self.aria2_connections: int | None = None
        self.aria2_fallback_native: bool = False
        self.download_attempt: int = 1
        self.download_method: str = "aria2c" if use_aria2c else "native"
        self.ignore_download_archive: bool = False
        self._settings_repo: Any | None = None
        self.force_impersonate: bool = False
        self.use_generic_extractors: bool = False
        self.recovery_steps: list[str] = []

    def _staging_dir(self) -> Path:
        from frameforge.paths import frameforge_root, temp_dir

        dest = temp_dir() / "dl"
        try:
            Path(self.output_dir).resolve().relative_to(frameforge_root().resolve())
        except ValueError:
            dest = Path(self.output_dir) / ".ff-temp"
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def _yt_paths(self) -> dict[str, str]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return {"home": str(self.output_dir), "temp": str(self._staging_dir())}

    def _relocate_sidecars(self, media: Path) -> None:
        """Move .info.json beside the finished file into FrameForge/metadata/."""
        import shutil

        from frameforge.library.paths import unique_dest
        from frameforge.paths import metadata_dir

        if media is None or not Path(media).exists():
            return
        media = Path(media)
        dest_dir = metadata_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        for cand in (
            media.with_suffix(media.suffix + ".info.json"),
            media.with_name(media.stem + ".info.json"),
        ):
            if not cand.is_file():
                continue
            dest = unique_dest(dest_dir, cand.name)
            shutil.move(str(cand), str(dest))

    OUTTMPL_REL = "%(title).200B [%(id)s].%(ext)s"

    def _speed_repo(self) -> Any | None:
        return getattr(self, "_settings_repo", None)

    def _concurrent_fragments(self) -> int:
        from frameforge.download.throughput import concurrent_fragments

        if self.concurrent_fragments is not None:
            return int(self.concurrent_fragments)
        return concurrent_fragments(self._speed_repo())

    def _aria2_connections(self) -> int:
        from frameforge.download.throughput import aria2_connections

        if self.aria2_connections is not None:
            return int(self.aria2_connections)
        return aria2_connections(self._speed_repo())

    def _aria2c_enabled(self) -> bool:
        from frameforge.download.invocation import aria2c_available

        return bool(self.use_aria2c) and aria2c_available()

    def _valid_cookiefile(self) -> Path | None:
        from frameforge.download.cookies import is_netscape_cookie_text

        if not self.cookiefile:
            return None
        path = Path(self.cookiefile)
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        if not is_netscape_cookie_text(text):
            return None
        return path

    def _format_selector(self) -> str:
        from frameforge.download.formats import resolve_format_selector

        return resolve_format_selector(self.format_preference)

    def _extractor_args_cli(self, url: str) -> str | None:
        from frameforge.download.youtube_clients import extractor_args_cli

        if not self.youtube_innertube:
            return None
        return extractor_args_cli(
            url,
            repo=self._settings_repo,
            clients=self.youtube_player_clients,
        )

    def extract_info(self, url: str) -> dict[str, Any]:
        from yt_dlp import YoutubeDL

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 12,
        }
        if self._valid_cookiefile() is not None:
            opts["cookiefile"] = str(self._valid_cookiefile())
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict):
            raise RuntimeError("extract_info returned non-dict")
        return info

    def build_opts(self, progress_cb: ProgressCb | None = None, *, url: str | None = None) -> dict[str, Any]:
        outtmpl = self.OUTTMPL_REL

        def _hook(d: dict[str, Any]) -> None:
            if not progress_cb:
                return
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = 0.0
                if total:
                    pct = max(0.0, min(100.0, downloaded * 100.0 / total))
                speed = d.get("speed")
                eta = d.get("eta")
                # Prefer yt-dlp preformatted strings when present
                speed_str = d.get("_speed_str") or _format_speed(
                    float(speed) if speed is not None else None
                )
                eta_str = d.get("_eta_str") or _format_eta(
                    float(eta) if eta is not None else None
                )
                progress_cb(
                    pct,
                    {
                        "speed_bps": float(speed) if speed is not None else None,
                        "eta_seconds": float(eta) if eta is not None else None,
                        "speed_str": speed_str,
                        "eta_str": eta_str,
                    },
                )
            elif d.get("status") == "finished":
                progress_cb(
                    100.0,
                    {
                        "speed_bps": None,
                        "eta_seconds": 0,
                        "speed_str": "—",
                        "eta_str": "00:00",
                    },
                )

        opts: dict[str, Any] = {
            "outtmpl": outtmpl,
            "paths": self._yt_paths(),
            "format": self._format_selector(),
            "merge_output_format": "mp4",
            "continuedl": True,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
            "writedescription": False,
            "writeinfojson": True,
            "retries": 5,
            "fragment_retries": 5,
            "ignoreerrors": False,
            "progress_hooks": [_hook],
            "postprocessors": [
                {"key": "FFmpegMetadata", "add_metadata": True},
            ],
        }
        cookie = self._valid_cookiefile()
        if cookie is not None:
            opts["cookiefile"] = str(cookie)
        from frameforge.download.throughput import (
            aria2c_opt_args,
            http_chunk_size_bytes,
            throttled_rate_bps,
        )

        opts["concurrent_fragment_downloads"] = self._concurrent_fragments()
        opts["throttledratelimit"] = throttled_rate_bps()
        opts["http_chunk_size"] = http_chunk_size_bytes()
        if self._aria2c_enabled():
            opts["external_downloader"] = {"default": "aria2c"}
            opts["external_downloader_args"] = {
                "aria2c": aria2c_opt_args(self._aria2_connections())
            }
        if not self.ignore_download_archive:
            opts["download_archive"] = str(self.archive_file)
        self._apply_rate_opts(opts)
        args = self._extractor_args_cli(url or "")
        if args:
            from frameforge.download.youtube_clients import extractor_args_opts

            parsed = extractor_args_opts(url or "https://www.youtube.com/", clients=args.split("=", 1)[-1])
            if parsed:
                opts["extractor_args"] = parsed
        if url:
            from frameforge.download.impersonate import impersonate_ydl_option

            impersonate = impersonate_ydl_option(
                url, repo=self._settings_repo, force=bool(self.force_impersonate)
            )
            if impersonate is not None:
                opts["impersonate"] = impersonate
        if self.use_generic_extractors:
            opts["allowed_extractors"] = ["generic", "default"]
        return opts

    def _apply_rate_opts(self, opts: dict[str, Any]) -> None:
        if getattr(self, "sleep_interval", None):
            opts["sleep_interval"] = float(self.sleep_interval)
            opts["max_sleep_interval"] = float(getattr(self, "max_sleep_interval", 5) or 5)
        if getattr(self, "limit_rate_bps", None):
            opts["ratelimit"] = int(self.limit_rate_bps)

    def download(
        self,
        url: str,
        progress_cb: ProgressCb | None = None,
        *,
        job_id: int | None = None,
        process_registry: ProcessRegistry | None = None,
    ) -> DownloadResult:
        """Download *url*.

        When *process_registry* and *job_id* are provided, yt-dlp runs as a
        killable subprocess (hard cancel via process-tree kill). Otherwise the
        in-process YoutubeDL API is used (direct/unit callers).

        If aria2c hits googlevideo HTTP 403 / exit 22, retry once with the native
        downloader. Cancel/pause still abort immediately.
        """
        from frameforge.errors import is_aria2_forbidden

        original_aria2 = self.use_aria2c
        self.aria2_fallback_native = False
        self.download_attempt = 1
        used_aria2 = self._aria2c_enabled()
        self.download_method = "aria2c" if used_aria2 else "native"
        try:
            try:
                return self._download_once(
                    url, progress_cb, job_id=job_id, process_registry=process_registry
                )
            except (DownloadCancelled, DownloadPaused):
                raise
            except Exception as exc:
                if not used_aria2 or not is_aria2_forbidden(str(exc)):
                    raise
                self.use_aria2c = False
                self.aria2_fallback_native = True
                self.download_attempt = 2
                self.download_method = "native"
                if progress_cb:
                    progress_cb(
                        0.0,
                        {
                            "speed_bps": None,
                            "eta_seconds": None,
                            "speed_str": "CDN blocked aria2 — retrying built-in…",
                            "eta_str": None,
                        },
                    )
                return self._download_once(
                    url, progress_cb, job_id=job_id, process_registry=process_registry
                )
        finally:
            self.use_aria2c = original_aria2

    def _download_once(
        self,
        url: str,
        progress_cb: ProgressCb | None = None,
        *,
        job_id: int | None = None,
        process_registry: ProcessRegistry | None = None,
    ) -> DownloadResult:
        self.describe_cli_invocation(url)
        if process_registry is not None and job_id is not None:
            return self._download_subprocess(
                url,
                progress_cb,
                job_id=job_id,
                process_registry=process_registry,
            )
        return self._download_inprocess(url, progress_cb)

    def _download_inprocess(
        self, url: str, progress_cb: ProgressCb | None = None
    ) -> DownloadResult:
        from yt_dlp import YoutubeDL

        opts = self.build_opts(progress_cb, url=url)
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise RuntimeError("Download skipped or failed (no info returned)")
            path = Path(ydl.prepare_filename(info))
            if not path.exists():
                for ext in (".mp4", ".mkv", ".webm", ".m4a"):
                    candidate = path.with_suffix(ext)
                    if candidate.exists():
                        path = candidate
                        break
            if not path.exists():
                requested = info.get("requested_downloads") or []
                if requested and requested[0].get("filepath"):
                    path = Path(requested[0]["filepath"])
            if not path.exists():
                from frameforge.download.output_path import require_download_artifact

                resolved = require_download_artifact(
                    url=url,
                    output_dir=self.output_dir,
                    printed=[str(path)] if path else [],
                    archive_file=None if self.ignore_download_archive else self.archive_file,
                )
                path = resolved.path  # type: ignore[assignment]
                self._record_path_recovery(resolved)
            title = str(info.get("title") or path.stem)
            self._relocate_sidecars(path)
            return DownloadResult(path=path, title=title, info=info)

    def _build_cli_cmd(self, url: str) -> list[str]:
        paths = self._yt_paths()
        outtmpl = self.OUTTMPL_REL
        cmd: list[str] = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--newline",
            "--continue",
            "--progress",
            "--no-colors",
            "--no-playlist",
            "-f",
            self._format_selector(),
            "--merge-output-format",
            "mp4",
            "-P",
            f"home:{paths['home']}",
            "-P",
            f"temp:{paths['temp']}",
            "-o",
            outtmpl,
            "--write-info-json",
            "--write-thumbnail",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--print",
            "after_move:%(filepath)s",
            "--print",
            "%(filepath)s",
            "--print",
            "%(title)s",
            "--print",
            "%(extractor_key)s",
            "--print",
            "%(id)s",
        ]
        if not self.ignore_download_archive:
            cmd.extend(["--download-archive", str(self.archive_file)])
        cookie = self._valid_cookiefile()
        if cookie is not None:
            cmd.extend(["--cookies", str(cookie)])
        from frameforge.download.invocation import ffmpeg_location
        from frameforge.download.throughput import (
            DEFAULT_HTTP_CHUNK_SIZE,
            DEFAULT_THROTTLED_RATE,
            aria2c_cli_args,
        )

        ffmpeg = ffmpeg_location()
        if ffmpeg:
            cmd.extend(["--ffmpeg-location", str(Path(ffmpeg).parent)])
        cmd.extend(["--concurrent-fragments", str(self._concurrent_fragments())])
        cmd.extend(["--throttled-rate", DEFAULT_THROTTLED_RATE])
        cmd.extend(["--http-chunk-size", DEFAULT_HTTP_CHUNK_SIZE])
        if self._aria2c_enabled():
            cmd.extend(
                [
                    "--downloader",
                    "aria2c",
                    "--downloader-args",
                    f"aria2c:{aria2c_cli_args(self._aria2_connections())}",
                ]
            )
        if self.sleep_interval:
            cmd.extend(["--sleep-interval", str(self.sleep_interval)])
            cmd.extend(["--max-sleep-interval", str(self.max_sleep_interval)])
        if self.limit_rate_bps:
            cmd.extend(["--limit-rate", str(int(self.limit_rate_bps))])
        from frameforge.download.js_runtime import js_runtime_cli_args

        cmd.extend(js_runtime_cli_args())
        from frameforge.download.impersonate import impersonate_cli_args

        cmd.extend(
            impersonate_cli_args(
                url,
                repo=self._settings_repo,
                force=bool(self.force_impersonate),
            )
        )
        extractor = self._extractor_args_cli(url)
        if extractor:
            cmd.extend(["--extractor-args", extractor])
        if self.use_generic_extractors:
            from frameforge.download.recovery import GENERIC_EXTRACTORS_CLI

            cmd.extend(["--use-extractors", GENERIC_EXTRACTORS_CLI])
        cmd.append(url)
        return cmd

    def describe_cli_invocation(self, url: str) -> dict[str, Any]:
        """Same argv/cwd/env the subprocess path will use (no process started)."""
        from frameforge.download.invocation import (
            download_subprocess_env,
            ffmpeg_location,
            snapshot_invocation,
        )

        cmd = self._build_cli_cmd(url)
        _env, overrides = download_subprocess_env()
        cookie = self._valid_cookiefile()
        from frameforge.download.throughput import (
            DEFAULT_HTTP_CHUNK_SIZE,
            DEFAULT_THROTTLED_RATE,
            aria2c_cli_args,
        )

        extractor = self._extractor_args_cli(url)
        aria2_on = self._aria2c_enabled()
        snap = snapshot_invocation(
            argv=cmd,
            cwd=str(self.output_dir),
            output_template=self.OUTTMPL_REL,
            cookies=str(cookie) if cookie is not None else None,
            aria2c=aria2_on,
            format_selector=self._format_selector(),
            env_overrides=overrides,
            ffmpeg=ffmpeg_location(),
        )
        snap["cookies_attached"] = cookie is not None
        snap["concurrent_fragments"] = self._concurrent_fragments()
        snap["throttled_rate"] = DEFAULT_THROTTLED_RATE
        snap["http_chunk_size"] = DEFAULT_HTTP_CHUNK_SIZE
        snap["aria2_args"] = aria2c_cli_args(self._aria2_connections()) if aria2_on else None
        snap["player_client"] = extractor
        js_args = [a for i, a in enumerate(cmd) if a == "--js-runtimes" or (i and cmd[i - 1] == "--js-runtimes")]
        snap["js_runtimes"] = js_args[1] if len(js_args) > 1 else (overrides.get("js_runtime") if overrides else None)
        impersonate_val = None
        if "--impersonate" in cmd:
            idx = cmd.index("--impersonate")
            if idx + 1 < len(cmd):
                impersonate_val = cmd[idx + 1]
        snap["impersonate"] = impersonate_val
        snap["use_extractors"] = (
            cmd[cmd.index("--use-extractors") + 1] if "--use-extractors" in cmd else None
        )
        if cookie is not None:
            log.info("ytdlp_invocation cookiefile attached: %s", cookie)
        else:
            log.info(
                "ytdlp_invocation cookiefile not attached (missing, empty, or header-only)"
            )
        self.last_invocation = snap
        return snap

    def _record_path_recovery(self, resolved: Any) -> None:
        snap = self.last_invocation if isinstance(self.last_invocation, dict) else {}
        snap["resolved_path"] = str(resolved.path) if getattr(resolved, "path", None) else None
        snap["recovery_method"] = getattr(resolved, "recovery_method", None)
        snap["archive_hit"] = bool(getattr(resolved, "archive_hit", False))
        self.last_invocation = snap

    def _download_subprocess(
        self,
        url: str,
        progress_cb: ProgressCb | None,
        *,
        job_id: int,
        process_registry: ProcessRegistry,
    ) -> DownloadResult:
        import subprocess
        import threading

        from frameforge.download.invocation import download_subprocess_env

        cmd = self._build_cli_cmd(url)
        env, overrides = download_subprocess_env()
        snap = self.describe_cli_invocation(url)
        snap["env_overrides"] = overrides
        creationflags = popen_creationflags()
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "bufsize": 0,
            "creationflags": creationflags,
            "cwd": str(self.output_dir),
            "env": env,
        }
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
            kwargs.pop("creationflags", None)

        proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
        process_registry.register(job_id, proc.pid)
        if process_registry.was_paused(job_id):
            raise DownloadPaused("paused")
        if process_registry.was_killed(job_id):
            raise DownloadCancelled("cancelled")
        printed: list[str] = []
        output_tail: list[str] = []
        stderr_chunks: list[str] = []

        def _drain_stderr() -> None:
            stream = proc.stderr
            if stream is None:
                return
            try:
                data = stream.read()
            except Exception:  # noqa: BLE001
                return
            if not data:
                return
            text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
            if text:
                stderr_chunks.append(text)

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()
        try:
            assert proc.stdout is not None
            for raw in iter_subprocess_text_chunks(proc.stdout):
                line = raw.rstrip("\n\r")
                if line:
                    output_tail.append(line)
                    if len(output_tail) > 40:
                        del output_tail[0]
                if process_registry.was_paused(job_id):
                    raise DownloadPaused("paused")
                if process_registry.was_killed(job_id):
                    raise DownloadCancelled("cancelled")
                parsed = parse_cli_progress_line(line)
                if progress_cb and parsed is not None:
                    speed_str = parsed["speed_str"]
                    eta_str = parsed["eta_str"]
                    progress_cb(
                        parsed["percent"],
                        {
                            "speed_bps": parsed["speed_bps"],
                            "eta_seconds": parsed["eta_seconds"],
                            "speed_str": speed_str if speed_str != "—" else None,
                            "eta_str": eta_str if eta_str != "—" else None,
                        },
                    )
                if line and not line.startswith("["):
                    from frameforge.download.output_path import looks_like_filepath_line

                    if looks_like_filepath_line(line) or (
                        "ETA" not in line and "at " not in line and "%" not in line and line not in printed
                    ):
                        if line not in printed:
                            printed.append(line)
            rc = proc.wait()
            err_thread.join(timeout=5)
            stderr_text = "".join(stderr_chunks)
            for err_line in iter_progress_lines(stderr_text):
                output_tail.append(err_line)
                if len(output_tail) > 80:
                    del output_tail[0]
            snap["returncode"] = rc
            snap["stderr_empty"] = not bool(stderr_text.strip() or output_tail)
            self.last_invocation = snap
            if process_registry.was_paused(job_id):
                raise DownloadPaused("paused")
            if process_registry.was_killed(job_id):
                raise DownloadCancelled("cancelled")
            if rc != 0:
                from frameforge.errors import format_ytdlp_exit_error

                raise RuntimeError(
                    format_ytdlp_exit_error(rc, output_tail or printed, argv=cmd)
                )
        except (DownloadCancelled, DownloadPaused):
            if proc.poll() is None:
                process_registry.kill(job_id)
                try:
                    proc.wait(timeout=15)
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            if proc.poll() is None:
                process_registry.kill(job_id)
                try:
                    proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            process_registry.unregister(job_id)

        from frameforge.download.output_path import (
            OutputMissingError,
            ResolvedOutput,
            looks_like_filepath_line,
            require_download_artifact,
            video_id_from_url,
        )

        try:
            resolved = require_download_artifact(
                url=url,
                output_dir=self.output_dir,
                printed=printed,
                output_tail=output_tail + stderr_chunks,
                archive_file=None if self.ignore_download_archive else self.archive_file,
            )
        except OutputMissingError as exc:
            self._record_path_recovery(
                ResolvedOutput(None, "missing", exc.archive_hit, video_id_from_url(url))
            )
            raise
        self._record_path_recovery(resolved)
        path = resolved.path
        assert path is not None
        title = ""
        extractor = ""
        video_id = resolved.video_id or ""
        non_files = [x for x in printed if not Path(x).is_file() and not looks_like_filepath_line(x)]
        if non_files:
            title = non_files[0]
            if len(non_files) >= 2:
                extractor = non_files[1]
            if len(non_files) >= 3:
                video_id = video_id or non_files[2]

        infojson = path.with_suffix(path.suffix + ".info.json")
        if not infojson.exists():
            infojson = path.with_name(path.stem + ".info.json")
        info: dict[str, Any] = {}
        if infojson.exists():
            import json

            try:
                info = json.loads(infojson.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                info = {}
        title = str(info.get("title") or title or path.stem)
        if extractor:
            info.setdefault("extractor_key", extractor)
        if video_id:
            info.setdefault("id", video_id)
        if progress_cb:
            progress_cb(
                100.0,
                {
                    "speed_bps": None,
                    "eta_seconds": 0,
                    "speed_str": "—",
                    "eta_str": "00:00",
                },
            )
        self._relocate_sidecars(path)
        return DownloadResult(path=path, title=title, info=info)

    def is_in_archive(self, url: str) -> bool:
        if not self.archive_file.exists():
            return False
        text = self.archive_file.read_text(encoding="utf-8", errors="ignore")
        return url in text
