"""yt-dlp based downloader with aria2c, resume, archive, and rich progress."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from frameforge.paths import archive_dir, downloads_dir, ensure_output_tree


ProgressCb = Callable[[float, dict[str, Any]], None]


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


@dataclass
class DownloadResult:
    path: Path
    title: str
    info: dict[str, Any]


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

    def _format_selector(self) -> str:
        if self.format_preference and self.format_preference != "best":
            return self.format_preference
        return "bv*+ba/b"

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
                "aria2c": ["-x", "8", "-s", "8", "-k", "1M", "--file-allocation=none"]
            }
        return opts

    def download(self, url: str, progress_cb: ProgressCb | None = None) -> DownloadResult:
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

    def is_in_archive(self, url: str) -> bool:
        if not self.archive_file.exists():
            return False
        text = self.archive_file.read_text(encoding="utf-8", errors="ignore")
        return url in text
