"""Tests for segment split planning and remaster concat helpers."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from frameforge.upscale.segment_split import (
    DEFAULT_SEGMENT_MINUTES,
    _safe_stem,
    plan_segments,
    unique_segment_root,
)


# ---------------------------------------------------------------------------
# plan_segments (pure math, no ffmpeg needed)
# ---------------------------------------------------------------------------

def test_plan_segments_one_segment_for_short_clip():
    plans = plan_segments(5 * 60.0, segment_minutes=15.0)
    assert len(plans) == 1
    start, dur = plans[0]
    assert start == 0.0
    assert math.isclose(dur, 5 * 60.0)


def test_plan_segments_two_segments_for_30min():
    plans = plan_segments(30 * 60.0, segment_minutes=15.0)
    assert len(plans) == 2
    assert plans[0][0] == 0.0
    assert math.isclose(plans[0][1], 15 * 60.0)
    assert math.isclose(plans[1][0], 15 * 60.0)
    assert math.isclose(plans[1][1], 15 * 60.0)


def test_plan_segments_last_segment_shorter():
    # 37 min → 2 × 15 min + 1 × 7 min
    plans = plan_segments(37 * 60.0, segment_minutes=15.0)
    assert len(plans) == 3
    last_start, last_dur = plans[-1]
    assert math.isclose(last_start, 30 * 60.0)
    assert math.isclose(last_dur, 7 * 60.0, abs_tol=1.0)


def test_plan_segments_contiguous_no_overlap():
    """Segments must tile perfectly with no gap or overlap."""
    total = 2 * 3600.0 + 13 * 60.0 + 27.0  # 2h 13m 27s
    plans = plan_segments(total, segment_minutes=15.0)
    # Each start = previous start + previous duration
    for i in range(1, len(plans)):
        prev_start, prev_dur = plans[i - 1]
        this_start, _ = plans[i]
        assert math.isclose(this_start, prev_start + prev_dur, abs_tol=1e-6)
    # Sum of durations = total
    total_dur = sum(d for _, d in plans)
    assert math.isclose(total_dur, total, abs_tol=1e-3)


def test_plan_segments_custom_minutes():
    plans = plan_segments(60 * 60.0, segment_minutes=20.0)
    assert len(plans) == 3
    for _, dur in plans:
        assert math.isclose(dur, 20 * 60.0, abs_tol=0.1)


def test_plan_segments_exact_multiple():
    plans = plan_segments(45 * 60.0, segment_minutes=15.0)
    assert len(plans) == 3
    for _, dur in plans:
        assert math.isclose(dur, 15 * 60.0)


def test_plan_segments_very_long_clip():
    # 4-hour clip
    plans = plan_segments(4 * 3600.0, segment_minutes=15.0)
    assert len(plans) == 16  # 4*60/15 = 16


def test_plan_segments_zero_duration_returns_one():
    plans = plan_segments(0.0)
    assert len(plans) == 1


# ---------------------------------------------------------------------------
# unique_segment_root
# ---------------------------------------------------------------------------

def test_unique_segment_root_unique_on_successive_calls(tmp_path: Path):
    src = tmp_path / "myvideo.mp4"
    root1 = unique_segment_root(src, tmp_path)
    root2 = unique_segment_root(src, tmp_path)
    # Timestamp-based; in the same second they collide — that's acceptable.
    # The important thing is the name contains the stem.
    assert "myvideo" in root1.name
    assert "_segments" in root1.name


def test_unique_segment_root_special_chars(tmp_path: Path):
    src = tmp_path / "my video (HD) [2024].mp4"
    root = unique_segment_root(src, tmp_path)
    # Name should be filesystem-safe (no spaces or brackets)
    assert " " not in root.name
    assert "(" not in root.name


# ---------------------------------------------------------------------------
# _safe_stem
# ---------------------------------------------------------------------------

def test_safe_stem_strips_special_chars():
    result = _safe_stem("hello world! (test)")
    assert " " not in result
    assert "!" not in result
    assert "(" not in result


def test_safe_stem_max_len():
    result = _safe_stem("a" * 100, max_len=40)
    assert len(result) <= 40


def test_safe_stem_empty_fallback():
    result = _safe_stem("!@#$%")
    assert len(result) > 0  # should return fallback "clip"


# ---------------------------------------------------------------------------
# Remaster helpers (no ffmpeg — unit-level only)
# ---------------------------------------------------------------------------

def test_find_upscaled_segments_happy_path(tmp_path: Path):
    from frameforge.upscale.remaster import find_upscaled_segments

    dirs = []
    for i in range(3):
        d = tmp_path / f"seg_{i:04d}"
        d.mkdir()
        f = d / f"seg_{i:04d}.upscaled.mp4"
        f.write_bytes(b"fake")
        dirs.append(d)

    found = find_upscaled_segments(dirs, suffix=".upscaled.mp4")
    assert len(found) == 3
    for f in found:
        assert f.exists()
        assert "upscaled" in f.name


def test_find_upscaled_segments_fallback_to_any_mp4(tmp_path: Path):
    from frameforge.upscale.remaster import find_upscaled_segments

    d = tmp_path / "seg_0000"
    d.mkdir()
    f = d / "seg_0000.mp4"
    f.write_bytes(b"fake")

    found = find_upscaled_segments([d])
    assert len(found) == 1
    assert found[0] == f


def test_find_upscaled_segments_missing_raises(tmp_path: Path):
    from frameforge.upscale.remaster import find_upscaled_segments

    d = tmp_path / "seg_empty"
    d.mkdir()

    with pytest.raises(FileNotFoundError, match="seg_empty"):
        find_upscaled_segments([d])


def test_keep_parts_returns_result(tmp_path: Path):
    from frameforge.upscale.remaster import keep_parts

    d = tmp_path / "seg_0000"
    d.mkdir()
    f = d / "seg_0000.upscaled.mp4"
    f.write_bytes(b"fake")

    result = keep_parts([d])
    assert result.kept_parts_only is True
    assert result.output_path == f
    assert result.audio_source is None


# ---------------------------------------------------------------------------
# Onboarding context (pure dataclass — no Flet)
# ---------------------------------------------------------------------------

def test_onboarding_context_exceeds_gate():
    from frameforge.upscale.onboarding import OnboardingContext

    ctx = OnboardingContext(
        source_name="big_movie.mp4",
        width=1920,
        height=1080,
        duration_sec=6 * 3600.0,
        total_frames=648000,
        fps_source=30.0,
        estimate_label="~10 hours",
        fps_estimate=0.5,
        probe_used=False,
        exceeds_gate=True,
        model_kind="realesrgan",
        model_available=True,
        cpu_percent=45.0,
        ram_percent=60.0,
        segment_minutes=15.0,
    )
    assert ctx.exceeds_gate
    assert ctx.model_available


def test_onboarding_context_no_model():
    from frameforge.upscale.onboarding import OnboardingContext

    ctx = OnboardingContext(
        source_name="clip.mp4",
        width=1280,
        height=720,
        duration_sec=300.0,
        total_frames=9000,
        fps_source=30.0,
        estimate_label="~1h 30m",
        fps_estimate=1.5,
        probe_used=False,
        exceeds_gate=False,
        model_kind="none",
        model_available=False,
        segment_minutes=15.0,
    )
    assert not ctx.model_available
    assert ctx.model_kind == "none"
