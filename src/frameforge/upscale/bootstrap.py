"""Ensure the models directory exists; optionally write a smoke Identity ONNX.

Smoke Identity is **not** Real-ESRGAN. It exists so the GUI and ONNX session
probes work on dev machines when no weights have been downloaded.
"""

from __future__ import annotations

import logging
from pathlib import Path

from frameforge.paths import models_dir

log = logging.getLogger(__name__)

SMOKE_NAME = "frameforge_smoke_identity.onnx"
_LOGGED_EMPTY = False


def list_onnx(root: Path | None = None) -> list[Path]:
    folder = Path(root) if root is not None else models_dir()
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.onnx") if p.is_file())


def maybe_create_smoke_onnx(root: Path | None = None) -> Path | None:
    """Write Identity ONNX if the models dir has none. Best-effort; never raises."""
    folder = Path(root) if root is not None else models_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        existing = list_onnx(folder)
        if existing:
            return None
        dest = folder / SMOKE_NAME
        from onnx import TensorProto, helper, save_model

        x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 8, 8])
        y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, 8, 8])
        node = helper.make_node("Identity", ["input"], ["output"])
        graph = helper.make_graph([node], "ff_smoke", [x], [y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
        model.ir_version = 8
        save_model(model, dest)
        log.info(
            "Created smoke Identity ONNX at %s (not Real-ESRGAN; 2× uses interpolation).",
            dest,
        )
        return dest
    except Exception:  # noqa: BLE001
        log.warning("Could not auto-create smoke ONNX under %s", folder, exc_info=True)
        return None


def bootstrap_models(root: Path | None = None) -> Path:
    """Create models dir; if empty, log once and try a smoke Identity ONNX."""
    global _LOGGED_EMPTY
    folder = Path(root) if root is not None else models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if not list_onnx(folder):
        if not _LOGGED_EMPTY:
            log.warning(
                "No ONNX model under %s — attempting smoke Identity (not Real-ESRGAN). "
                "For Real-ESRGAN weights: python .\\scripts\\download_models.py",
                folder,
            )
            _LOGGED_EMPTY = True
        maybe_create_smoke_onnx(folder)
    return folder
