"""Upscale eligibility checks (resolution guards)."""

from __future__ import annotations

from pathlib import Path

from frameforge.upscale.ffmpeg_utils import video_size

# Block 4K and above (UHD height)
MIN_BLOCK_HEIGHT = 2160


class UpscaleBlockedError(RuntimeError):
    """Raised when a source video must not be upscaled."""


def assert_upscale_allowed(source: Path) -> tuple[int, int]:
    """Probe source size; raise UpscaleBlockedError if height >= 2160.

    Returns (width, height) when allowed.
    """
    source = Path(source)
    width, height = video_size(source)
    if height >= MIN_BLOCK_HEIGHT:
        raise UpscaleBlockedError(
            f"Blocked: source is 4K/≥2160p (height={height})"
        )
    return width, height
