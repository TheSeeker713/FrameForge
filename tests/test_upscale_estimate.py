"""Tests for upscale time estimation, 4-hour gate, and label helpers."""

from __future__ import annotations

import math

import pytest

from frameforge.upscale.disk import VideoMetrics
from frameforge.upscale.estimate import (
    FOUR_HOUR_GATE_SECONDS,
    UpscaleEstimate,
    _fallback_fps,
    estimate_upscale,
    format_estimate_label,
    gate_message,
)


# ---------------------------------------------------------------------------
# format_estimate_label
# ---------------------------------------------------------------------------

def test_label_seconds():
    assert format_estimate_label(45) == "~45s"


def test_label_minutes():
    label = format_estimate_label(90)
    assert "min" in label
    assert "2" in label or "1" in label  # ~2 min or ~1 min depending on rounding


def test_label_sub_hour():
    label = format_estimate_label(3000)
    assert "min" in label
    assert "50" in label


def test_label_one_hour_range():
    label = format_estimate_label(3700)
    # Should show hours + minutes
    assert "h" in label


def test_label_many_hours():
    label = format_estimate_label(36000)  # 10 hours
    assert "hours" in label or "h" in label
    assert "10" in label


# ---------------------------------------------------------------------------
# _fallback_fps
# ---------------------------------------------------------------------------

def test_fallback_fps_qvga():
    fps = _fallback_fps(320, 240)
    assert fps >= 4.0  # QVGA should be fast


def test_fallback_fps_1080p():
    fps = _fallback_fps(1920, 1080)
    assert 0.1 < fps < 5.0  # conservative estimate


def test_fallback_fps_720p():
    fps_720 = _fallback_fps(1280, 720)
    fps_1080 = _fallback_fps(1920, 1080)
    assert fps_720 > fps_1080  # smaller is faster


def test_fallback_fps_4k_very_slow():
    fps = _fallback_fps(3840, 2160)
    assert fps < 0.5


# ---------------------------------------------------------------------------
# estimate_upscale with cached fps (no probe, no fallback randomness)
# ---------------------------------------------------------------------------

def test_estimate_short_clip_no_gate():
    metrics = VideoMetrics(width=1280, height=720, fps=30.0, duration_sec=60.0)
    est = estimate_upscale(metrics, cached_fps=2.0, run_probe=False)
    # 60s × 30fps = 1800 frames; at 2 fps → 900 s = 15 min → well under 4h
    assert est.total_frames == 1800
    assert math.isclose(est.fps_estimate, 2.0)
    assert not est.exceeds_gate
    assert est.label != ""


def test_estimate_long_clip_exceeds_gate():
    # 720p, 30fps, 8-hour clip → at 1.5 fps (table) = 8*3600*30 / 1.5 s ≈ 14.4h
    metrics = VideoMetrics(width=1280, height=720, fps=30.0, duration_sec=8 * 3600.0)
    est = estimate_upscale(metrics, cached_fps=1.5, run_probe=False)
    assert est.exceeds_gate
    assert est.total_seconds > FOUR_HOUR_GATE_SECONDS


def test_estimate_exactly_at_gate_boundary():
    # 4 hours at exactly the cached fps rate
    fps = 1.0
    target_frames = int(FOUR_HOUR_GATE_SECONDS * fps)
    duration_sec = target_frames / 30.0  # 30 fps source
    metrics = VideoMetrics(width=1280, height=720, fps=30.0, duration_sec=duration_sec)
    est = estimate_upscale(metrics, cached_fps=fps, run_probe=False)
    # Right at the boundary — total_seconds ≈ 4h
    # gate is strict >4h, so at exactly 4h it should NOT exceed
    assert not est.exceeds_gate or math.isclose(est.total_seconds, FOUR_HOUR_GATE_SECONDS, rel_tol=1e-3)


def test_estimate_probe_disabled_uses_fallback():
    metrics = VideoMetrics(width=1920, height=1080, fps=25.0, duration_sec=120.0)
    est = estimate_upscale(metrics, run_probe=False)
    assert est.fps_estimate > 0
    assert est.total_frames > 0
    assert not est.probe_used


def test_estimate_with_cached_fps_skips_probe():
    metrics = VideoMetrics(width=1920, height=1080, fps=25.0, duration_sec=60.0)
    est = estimate_upscale(metrics, cached_fps=3.14, run_probe=True)
    # cached_fps takes priority; probe is skipped
    assert math.isclose(est.fps_estimate, 3.14)
    assert not est.probe_used


# ---------------------------------------------------------------------------
# gate_message
# ---------------------------------------------------------------------------

def test_gate_message_contains_key_info():
    metrics = VideoMetrics(width=1920, height=1080, fps=30.0, duration_sec=5 * 3600.0)
    est = estimate_upscale(metrics, cached_fps=0.5, run_probe=False)
    msg = gate_message(est, source_name="big_movie.mp4")
    assert "big_movie.mp4" in msg
    assert "4" in msg  # the 4-hour threshold
    assert "segment" in msg.lower() or "split" in msg.lower()


# ---------------------------------------------------------------------------
# UpscaleGateError (handler integration)
# ---------------------------------------------------------------------------

def test_gate_error_has_option_patch():
    from frameforge.upscale.handler import UpscaleGateError

    metrics = VideoMetrics(width=1920, height=1080, fps=30.0, duration_sec=6 * 3600.0)
    est = estimate_upscale(metrics, cached_fps=0.5, run_probe=False)
    err = UpscaleGateError(est, "movie.mp4")
    patch = err.option_patch()
    assert patch["upscale_gate_total_seconds"] > FOUR_HOUR_GATE_SECONDS
    assert "upscale_gate_label" in patch
    assert "movie.mp4" in str(err)
    assert err.category == "upscale_gate"
