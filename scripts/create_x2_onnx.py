"""Create a tiny 2x Resize ONNX model for real upscale tests without external weights."""

from __future__ import annotations

import os
from pathlib import Path

from onnx import TensorProto, helper, numpy_helper
import numpy as np


def main() -> Path:
    root = Path(os.environ["USERPROFILE"]) / "Downloads" / "FrameForge" / "models"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / "frameforge_x2_resize.onnx"

    # input: NCHW float
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, ["N", "C", "H", "W"])
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, ["N", "C", "H2", "W2"])
    scales = numpy_helper.from_array(np.array([1.0, 1.0, 2.0, 2.0], dtype=np.float32), name="scales")
    node = helper.make_node(
        "Resize",
        inputs=["input", "", "scales"],
        outputs=["output"],
        mode="linear",
        coordinate_transformation_mode="asymmetric",
    )
    graph = helper.make_graph([node], "ff_x2", [x], [y], [scales])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    from onnx import save_model

    save_model(model, dest)
    print(dest, dest.stat().st_size)
    return dest


if __name__ == "__main__":
    main()
