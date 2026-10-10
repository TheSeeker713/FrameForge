"""Read video size and duration with ffprobe. Never raises. Never invents a duration."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 15


@dataclass
class ProbeResult:
    duration: float | None
    size: int | None
    width: int | None
    height: int | None
    vcodec: str | None
    pix_fmt: str | None
    fps: float | None
    rotation: int | None
    acodec: str | None
    color_transfer: str | None


def probe_file(path: str | Path) -> ProbeResult | None:
    src = Path(path)
    try:
        if not src.is_file():
            return None
    except OSError:
        return None
    try:
        from frameforge.download.invocation import ffprobe_location

        ffprobe = ffprobe_location()
    except Exception:  # noqa: BLE001
        log.exception("ffprobe lookup failed")
        return None
    if not ffprobe:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(  # noqa: S603
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(src),
            ],
            capture_output=True,
            timeout=_TIMEOUT,
            check=False,
            creationflags=flags,
        )
    except Exception:  # noqa: BLE001
        log.exception("ffprobe failed for %s", src)
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        payload = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    return _parse(payload)


def _parse(payload: dict) -> ProbeResult | None:
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    video = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"), None)
    if video is None and not fmt:
        return None
    width = _int(video.get("width")) if video else None
    height = _int(video.get("height")) if video else None
    rotation = _rotation(video) if video else None
    if rotation in {90, 270} and width and height:
        width, height = height, width
    return ProbeResult(
        duration=_float(fmt.get("duration")),
        size=_int(fmt.get("size")),
        width=width,
        height=height,
        vcodec=video.get("codec_name") if video else None,
        pix_fmt=video.get("pix_fmt") if video else None,
        fps=_fps(video.get("avg_frame_rate")) if video else None,
        rotation=rotation,
        acodec=audio.get("codec_name") if audio else None,
        color_transfer=video.get("color_transfer") if video else None,
    )


def _rotation(stream: dict) -> int | None:
    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    raw = tags.get("rotate")
    side = stream.get("side_data_list") if isinstance(stream.get("side_data_list"), list) else []
    for entry in side:
        if isinstance(entry, dict) and entry.get("rotation") is not None:
            raw = entry.get("rotation")
            break
    value = _int(raw)
    if value is None:
        return None
    return abs(value) % 360


def _fps(raw: object) -> float | None:
    if not isinstance(raw, str) or "/" not in raw:
        return _float(raw)
    num, den = raw.split("/", 1)
    top = _float(num)
    bottom = _float(den)
    if top is None or not bottom:
        return None
    return top / bottom


def _float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _int(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
