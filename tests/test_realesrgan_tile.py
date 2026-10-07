"""Real-ESRGAN x4plus is fixed at 128x128. Small tiles must be padded, then cropped."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from frameforge.paths import models_dir
from frameforge.upscale.onnx_upscaler import OnnxUpscaler


def test_realesrgan_pads_small_image_to_model_and_returns_4x():
    path = models_dir() / "RealESRGAN_x4plus.onnx"
    data = models_dir() / "real_esrgan_x4plus.data"
    if not path.is_file() or not data.is_file():
        pytest.skip("Real-ESRGAN weights are not installed")
    upscaler = OnnxUpscaler(model_path=path, tile=64)
    assert upscaler.scale == 4
    assert upscaler.input_height == 128
    image = np.zeros((32, 48, 3), dtype=np.uint8)
    image[:] = (20, 80, 160)
    out = upscaler.upscale_image(image)
    assert out.shape[0] == 128
    assert out.shape[1] == 192
    assert Path(upscaler.model_path).name == "RealESRGAN_x4plus.onnx"
