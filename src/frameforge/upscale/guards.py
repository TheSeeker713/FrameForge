"""Upscale eligibility checks (resolution guards)."""

from __future__ import annotations

from pathlib import Path

from frameforge.upscale.ffmpeg_utils import video_size

# Block 4K and above (UHD height)
MIN_BLOCK_HEIGHT = 2160
# Recommend upscale for SD/HD ready sources at or below 720p
RECOMMEND_MAX_HEIGHT = 720


class UpscaleBlockedError(RuntimeError):
    """Raised when a source video must not be upscaled."""


def is_upscale_recommended(height: int | None) -> bool:
    """Recommend 2× upscale when height is known and ≤ 720."""
    return height is not None and 0 < height <= RECOMMEND_MAX_HEIGHT


def is_upscale_blocked(height: int | None) -> bool:
    """True when height is known and ≥ 2160."""
    return height is not None and height >= MIN_BLOCK_HEIGHT


def assert_upscale_allowed(source: Path) -> tuple[int, int]:
    """Probe source size; raise UpscaleBlockedError if height >= 2160.

    Returns (width, height) when allowed. Duration and free-disk limits are
    enforced separately (see ``frameforge.upscale.disk`` / docs/UPSCALE_DISK.md).
    ≥2160p remains blocked; for 1080p the real risk is PNG temp size, not height.
    """
    source = Path(source)
    width, height = video_size(source)
    if height >= MIN_BLOCK_HEIGHT:
        raise UpscaleBlockedError(
            f"Blocked: source is 4K/≥2160p (height={height})"
        )
    return width, height
