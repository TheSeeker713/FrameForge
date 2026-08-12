"""Create a tiny Identity ONNX model for Phase 0 session smoke tests."""

from __future__ import annotations

import os
from pathlib import Path

from onnx import TensorProto, helper, save_model


def main() -> None:
    root = Path(os.environ["USERPROFILE"]) / "Downloads" / "FrameForge" / "models"
    root.mkdir(parents=True, exist_ok=True)
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 8, 8])
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, 8, 8])
    node = helper.make_node("Identity", ["input"], ["output"])
    graph = helper.make_graph([node], "ff_smoke", [x], [y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    dest = root / "frameforge_smoke_identity.onnx"
    save_model(model, dest)
    print(f"{dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
