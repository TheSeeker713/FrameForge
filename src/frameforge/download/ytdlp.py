"""yt-dlp based downloader with aria2c, resume, archive, and rich progress."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from frameforge.paths import archive_dir, downloads_dir, ensure_output_tree
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused, popen_creationflags

if TYPE_CHECKING:
    from frameforge.queue.process_registry import ProcessRegistry


ProgressCb = Callable[[float, dict[str, Any]], None]

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
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

    Returns None when the line is not a progress update (no usable percent).
    """
    line = _strip_ansi(line or "")
    if not line or "%" not in line:
        return None
    pct_m = _PCT_RE.search(line)
    if not pct_m:
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

    percent = max(0.0, min(100.0, float(pct_m.group(1))))
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

    def _format_selector(self) -> str:
        from frameforge.download.formats import resolve_format_selector

        return resolve_format_selector(self.format_preference)

    def extract_info(self, url: str) -> dict[str, Any]:
        from yt_dlp import YoutubeDL

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if self.cookiefile and Path(self.cookiefile).is_file():
            opts["cookiefile"] = str(self.cookiefile)
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict):
            raise RuntimeError("extract_info returned non-dict")
        return info

    def build_opts(self, progress_cb: ProgressCb | None = None) -> dict[str, Any]:
        outtmpl = str(self.output_dir / "%(title).200B [%(id)s].%(ext)s")

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
            "format": self._format_selector(),
            "merge_output_format": "mp4",
            "continuedl": True,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": False,
            "writedescription": False,
            "writeinfojson": True,
            "retries": 5,
            "fragment_retries": 5,
            "ignoreerrors": False,
            "download_archive": str(self.archive_file),
            "progress_hooks": [_hook],
            "postprocessors": [
                {"key": "FFmpegMetadata", "add_metadata": True},
            ],
        }
        if self.cookiefile and Path(self.cookiefile).is_file():
            opts["cookiefile"] = str(self.cookiefile)
        if self.use_aria2c:
            opts["external_downloader"] = {"default": "aria2c"}
            opts["external_downloader_args"] = {
                "aria2c": [
                    "-x",
                    "8",
                    "-s",
                    "8",
                    "-k",
                    "1M",
                    "--file-allocation=none",
                    "-c",
                    "--allow-overwrite=true",
                    "--auto-file-renaming=false",
                ]
            }
        else:
            # HLS/DASH fragments: one job still, multiple connections
            opts["concurrent_fragment_downloads"] = 8
        self._apply_rate_opts(opts)
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
        """
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

        opts = self.build_opts(progress_cb)
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
                raise FileNotFoundError(f"Downloaded file not found for {url}")
            title = str(info.get("title") or path.stem)
            return DownloadResult(path=path, title=title, info=info)

    def _build_cli_cmd(self, url: str) -> list[str]:
        outtmpl = str(self.output_dir / "%(title).200B [%(id)s].%(ext)s")
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
            "-o",
            outtmpl,
            "--download-archive",
            str(self.archive_file),
            "--write-info-json",
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
        if self.cookiefile and Path(self.cookiefile).is_file():
            cmd.extend(["--cookies", str(self.cookiefile)])
        if self.use_aria2c:
            cmd.extend(
                [
                    "--downloader",
                    "aria2c",
                    "--downloader-args",
                    "aria2c:-x 8 -s 8 -k 1M --file-allocation=none --summary-interval=1 --enable-color=false -c --allow-overwrite=true --auto-file-renaming=false",
                ]
            )
        if self.sleep_interval:
            cmd.extend(["--sleep-interval", str(self.sleep_interval)])
            cmd.extend(["--max-sleep-interval", str(self.max_sleep_interval)])
        if self.limit_rate_bps:
            cmd.extend(["--limit-rate", str(int(self.limit_rate_bps))])
        cmd.append(url)
        return cmd

    def _download_subprocess(
        self,
        url: str,
        progress_cb: ProgressCb | None,
        *,
        job_id: int,
        process_registry: ProcessRegistry,
    ) -> DownloadResult:
        import subprocess

        cmd = self._build_cli_cmd(url)
        creationflags = popen_creationflags()
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": 0,
            "creationflags": creationflags,
        }
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
            kwargs.pop("creationflags", None)

        proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
        process_registry.register(job_id, proc.pid)
        printed: list[str] = []
        output_tail: list[str] = []
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
                # yt-dlp --print lines have no [download] prefix typically
                if line and not line.startswith("[") and line not in printed:
                    if "ETA" not in line and "at " not in line and "%" not in line:
                        printed.append(line)
            rc = proc.wait(timeout=30)
            if process_registry.was_paused(job_id):
                raise DownloadPaused("paused")
            if process_registry.was_killed(job_id):
                raise DownloadCancelled("cancelled")
            if rc != 0:
                from frameforge.errors import format_ytdlp_exit_error

                raise RuntimeError(format_ytdlp_exit_error(rc, output_tail or printed))
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

        # Resolve output path from --print lines (filepath / after_move) or scan dir
        path: Path | None = None
        title = ""
        extractor = ""
        video_id = ""
        for item in printed:
            p = Path(item)
            if p.exists() and p.is_file():
                path = p
            elif not title and item and not item.startswith("http"):
                # Heuristic: first non-path print is often title; order is
                # filepath, title, extractor_key, id — overwrite carefully
                pass
        # --print order: after_move filepath, filepath, title, extractor_key, id
        # Prefer existing file paths from the end of printed list backwards
        files = [Path(x) for x in printed if Path(x).is_file()]
        if files:
            path = files[-1]
        if len(printed) >= 3:
            # Find title as the first printed non-file string after a file
            non_files = [x for x in printed if not Path(x).is_file()]
            if non_files:
                title = non_files[0]
                if len(non_files) >= 2:
                    extractor = non_files[1]
                if len(non_files) >= 3:
                    video_id = non_files[2]

        if path is None or not path.exists():
            # Fallback: newest media in output_dir modified in last few minutes
            candidates = sorted(
                [
                    p
                    for p in self.output_dir.glob("*")
                    if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a"}
                    and (time.time() - p.stat().st_mtime) < 600
                ],
                key=lambda p: p.stat().st_mtime,
            )
            if candidates:
                path = candidates[-1]
        if path is None or not path.exists():
            raise FileNotFoundError(f"Downloaded file not found for {url}")

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
        return DownloadResult(path=path, title=title, info=info)

    def is_in_archive(self, url: str) -> bool:
        if not self.archive_file.exists():
            return False
        text = self.archive_file.read_text(encoding="utf-8", errors="ignore")
        return url in text
