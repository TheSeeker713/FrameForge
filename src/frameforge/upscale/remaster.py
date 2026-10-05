"""Remaster: stitch upscaled segment files back into one output.

After a split-and-upscale workflow the user can either:
  - **Keep parts** – individual upscaled segments remain in their own sub-dirs.
  - **Concatenate** – all upscaled segments are losslessly joined and the
    original audio (from the source file) is remuxed into the final output.

Both paths are non-destructive: source and segment dirs are preserved unless
the caller explicitly requests cleanup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from frameforge.upscale.ffmpeg_utils import concat_segments, extract_audio, mux_video_audio

log = logging.getLogger(__name__)


@dataclass
class RemasterResult:
    output_path: Path
    segments_used: list[Path]
    audio_source: Path | None
    kept_parts_only: bool


def find_upscaled_segments(
    segment_dirs: list[Path],
    *,
    suffix: str = ".upscaled.mp4",
    fallback_glob: str = "*.mp4",
) -> list[Path]:
    """Return one upscaled video file per segment directory, in order.

    Looks for ``*<suffix>`` first, then any ``*.mp4``.  Raises if any
    segment directory has no candidate.
    """
    found: list[Path] = []
    for d in segment_dirs:
        d = Path(d)
        candidates = sorted(d.glob(f"*{suffix}"))
        if not candidates:
            candidates = sorted(d.glob(fallback_glob))
        if not candidates:
            raise FileNotFoundError(
                f"No upscaled video found in segment directory: {d}"
            )
        found.append(candidates[-1])
    return found


def concatenate_upscaled_segments(
    segment_dirs: list[Path],
    output_path: Path,
    *,
    audio_source: Path | None = None,
    job_id: int | None = None,
) -> RemasterResult:
    """Lossless-concat upscaled segments and remux original audio.

    Parameters
    ----------
    segment_dirs:
        Ordered list of per-segment output directories (each contains one
        upscaled mp4 produced by the normal upscale pipeline).
    output_path:
        Final remastered file path.
    audio_source:
        Original (pre-upscale) source video to pull audio from.  When None,
        the output will be video-only if no segments carry audio.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    upscaled = find_upscaled_segments(segment_dirs)
    log.info("Concatenating %d upscaled segment(s) → %s", len(upscaled), output_path)

    video_only = output_path.with_suffix(".video_only.mp4")
    concat_segments(upscaled, video_only, job_id=job_id)

    audio_path: Path | None = None
    if audio_source is not None:
        audio_tmp = output_path.parent / "_remaster_audio.m4a"
        audio_path = extract_audio(audio_source, audio_tmp, job_id=job_id)

    mux_video_audio(
        video_only,
        output_path,
        audio_path=audio_path,
        metadata_source=audio_source,
        job_id=job_id,
    )

    if video_only.exists():
        try:
            video_only.unlink()
        except OSError:
            pass

    return RemasterResult(
        output_path=output_path,
        segments_used=upscaled,
        audio_source=audio_source,
        kept_parts_only=False,
    )


def keep_parts(segment_dirs: list[Path]) -> RemasterResult:
    """Return a result that declares the parts are kept individually."""
    try:
        upscaled = find_upscaled_segments(segment_dirs)
    except FileNotFoundError:
        upscaled = []

    first = upscaled[0] if upscaled else Path(segment_dirs[0]) if segment_dirs else Path(".")
    return RemasterResult(
        output_path=first,
        segments_used=upscaled,
        audio_source=None,
        kept_parts_only=True,
    )
