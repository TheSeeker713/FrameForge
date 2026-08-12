"""Convert local media to MP3 via ffmpeg (VBR -q:a 2)."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from frameforge.paths import converted_dir, ensure_output_tree
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.ffmpeg_utils import probe
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused, popen_creationflags

# ffmpeg libmp3lame VBR quality (2 ≈ ~190 kbps). Documented in FORMATS_AND_CONVERT.md.
MP3_QUALITY = "2"
_TIME_RE = re.compile(r"out_time_ms=(\d+)")
_ALT_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def _duration_seconds(path: Path) -> float | None:
    try:
        info = probe(path)
        fmt = info.get("format") or {}
        dur = fmt.get("duration")
        if dur is not None:
            return float(dur)
        for stream in info.get("streams") or []:
            if stream.get("duration"):
                return float(stream["duration"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _pct_from_progress_line(line: str, duration_s: float | None) -> float | None:
    if duration_s is None or duration_s <= 0:
        return None
    m = _TIME_RE.search(line)
    if m:
        ms = int(m.group(1))
        return max(0.0, min(100.0, (ms / 1000.0) * 100.0 / duration_s))
    m = _ALT_TIME_RE.search(line)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        elapsed = h * 3600 + mi * 60 + s
        return max(0.0, min(100.0, elapsed * 100.0 / duration_s))
    return None


def convert_to_mp3(
    input_path: Path | str,
    output_path: Path | str | None = None,
    *,
    job_id: int | None = None,
    process_registry: ProcessRegistry | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Encode audio from *input_path* to MP3. Raises on missing input or ffmpeg failure."""
    src = Path(input_path)
    if not src.is_file():
        raise FileNotFoundError(f"ffmpeg: input not found: {src}")
    ensure_output_tree()
    dest = Path(output_path) if output_path else converted_dir() / f"{src.stem}.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    duration = _duration_seconds(src)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        MP3_QUALITY,
        "-progress",
        "pipe:1",
        "-nostats",
        str(dest),
    ]
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "creationflags": popen_creationflags(),
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
        kwargs.pop("creationflags", None)

    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    if process_registry is not None and job_id is not None:
        process_registry.register(job_id, proc.pid)
    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        err = proc.stderr
        if err is None:
            return
        try:
            stderr_chunks.append(err.read() or "")
        except Exception:  # noqa: BLE001
            pass

    err_thread = threading.Thread(target=_drain_stderr, daemon=True)
    err_thread.start()
    try:
        if progress_cb:
            progress_cb(0.0)
        stdout = proc.stdout
        if stdout is not None:
            for raw in stdout:
                pct = _pct_from_progress_line(raw.strip(), duration)
                if pct is not None and progress_cb:
                    progress_cb(pct)
        proc.wait()
        err_thread.join(timeout=5)
        if process_registry is not None and job_id is not None:
            if process_registry.was_paused(job_id):
                raise DownloadPaused("paused")
            if process_registry.was_killed(job_id):
                raise DownloadCancelled("cancelled")
        if proc.returncode != 0:
            err = "".join(stderr_chunks).strip() or "ffmpeg convert failed"
            raise RuntimeError(f"ffmpeg convert failed ({proc.returncode}): {err}")
        if not dest.is_file() or dest.stat().st_size <= 0:
            raise RuntimeError(f"ffmpeg convert produced empty output: {dest}")
        if progress_cb:
            progress_cb(100.0)
        return dest
    finally:
        if proc.poll() is None:
            if process_registry is not None and job_id is not None:
                process_registry.kill(job_id)
            else:
                proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
        if process_registry is not None and job_id is not None:
            process_registry.unregister(job_id)
