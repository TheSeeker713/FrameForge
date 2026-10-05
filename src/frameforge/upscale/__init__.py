"""ONNX video upscaling pipeline."""

from frameforge.upscale.estimate import (
    FOUR_HOUR_GATE_SECONDS,
    UpscaleEstimate,
    estimate_upscale,
    format_estimate_label,
    gate_message,
)
from frameforge.upscale.onboarding import OnboardingContext, build_onboarding_context
from frameforge.upscale.pipeline import UpscalePipeline, UpscaleResult
from frameforge.upscale.remaster import RemasterResult, concatenate_upscaled_segments, keep_parts
from frameforge.upscale.segment_split import (
    DEFAULT_SEGMENT_MINUTES,
    SplitResult,
    plan_segments,
    split_video_segments,
    unique_segment_root,
)

__all__ = [
    "FOUR_HOUR_GATE_SECONDS",
    "DEFAULT_SEGMENT_MINUTES",
    "OnboardingContext",
    "RemasterResult",
    "SplitResult",
    "UpscaleEstimate",
    "UpscalePipeline",
    "UpscaleResult",
    "build_onboarding_context",
    "concatenate_upscaled_segments",
    "estimate_upscale",
    "format_estimate_label",
    "gate_message",
    "keep_parts",
    "plan_segments",
    "split_video_segments",
    "unique_segment_root",
]
