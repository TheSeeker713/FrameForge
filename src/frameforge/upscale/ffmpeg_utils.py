"""Frame extract / assemble helpers via FFmpeg."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from frameforge.queue.process_registry import ProcessRegistry
from frameforge.util.process_tree import DownloadCancelled, popen_creationflags


def run_cmd(
    cmd: list[str],
    *,
    job_id: int | None = None,
    process_registry: ProcessRegistry | None = None,
) -> None:
    """Run a subprocess; when registry is provided, the PID is killable on cancel."""
    if process_registry is None or job_id is None:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
            )
        return

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
    process_registry.register(job_id, proc.pid)
    try:
        stdout, stderr = proc.communicate()
        if process_registry.was_killed(job_id):
            raise DownloadCancelled("cancelled")
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{stderr or stdout}"
            )
    finally:
        if proc.poll() is None:
            process_registry.kill(job_id)
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
        # Keep registration only while process is live; clear when done
        process_registry.unregister(job_id)


def probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def has_audio(path: Path) -> bool:
    data = probe(path)
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def video_size(path: Path) -> tuple[int, int]:
    data = probe(path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise RuntimeError(f"No video stream in {path}")


def extract_frames(
    video: Path,
    frames_dir: Path,
    *,
    max_frames: int | None = None,
    job_id: int | None = None,
    process_registry: ProcessRegistry | None = None,
) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%06d.png")
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vsync", "0"]
    if max_frames is not None:
        cmd.extend(["-frames:v", str(max_frames)])
    cmd.append(pattern)
    run_cmd(cmd, job_id=job_id, process_registry=process_registry)
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise RuntimeError(f"No frames extracted from {video}")
    return frames


def extract_audio(
    video: Path,
    audio_path: Path,
    *,
    job_id: int | None = None,
    process_registry: ProcessRegistry | None = None,
) -> Path | None:
    if not has_audio(video):
        return None
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    # Copy audio bitstream without re-encode when possible
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-c:a",
            "copy",
            str(audio_path),
        ],
        job_id=job_id,
        process_registry=process_registry,
    )
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        # fallback re-encode
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video),
                "-vn",
                "-c:a",
                "aac",
                str(audio_path.with_suffix(".m4a")),
            ],
            job_id=job_id,
            process_registry=process_registry,
        )
        return audio_path.with_suffix(".m4a")
    return audio_path


def assemble_video(
    frames_dir: Path,
    output: Path,
    *,
    fps: float,
    audio_path: Path | None = None,
    metadata_source: Path | None = None,
    job_id: int | None = None,
    process_registry: ProcessRegistry | None = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%06d.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        pattern,
    ]
    if audio_path and audio_path.exists():
        cmd.extend(["-i", str(audio_path)])
    if metadata_source and metadata_source.exists():
        cmd.extend(["-i", str(metadata_source), "-map_metadata", "2" if audio_path else "1"])
    cmd.extend(["-map", "0:v:0"])
    if audio_path and audio_path.exists():
        cmd.extend(["-map", "1:a:0", "-c:a", "copy"])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(output)])
    run_cmd(cmd, job_id=job_id, process_registry=process_registry)
    if not output.exists():
        raise RuntimeError(f"Failed to assemble {output}")
    return output


def detect_fps(video: Path) -> float:
    data = probe(video)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "25/1"
            if "/" in rate:
                num, den = rate.split("/", 1)
                den_f = float(den) or 1.0
                return max(1.0, float(num) / den_f)
            return float(rate)
    return 25.0
