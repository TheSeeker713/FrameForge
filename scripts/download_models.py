"""Download Real-ESRGAN ONNX if possible; always ensure a loadable ONNX exists."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from create_smoke_onnx import main as create_smoke


MODELS = Path(os.environ["USERPROFILE"]) / "Downloads" / "FrameForge" / "models"

CANDIDATES = [
    (
        "RealESRGAN_x4plus.onnx",
        "https://github.com/axodox/onnxruntime-extensions/releases/download/v1.0.0/realesrgan_x4.onnx",
    ),
]


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    existing = [p for p in MODELS.glob("*.onnx") if p.stat().st_size > 100]
    if any(p.name.startswith("RealESRGAN") for p in existing):
        print(f"Real-ESRGAN already present: {existing}")
        return

    for name, url in CANDIDATES:
        dest = MODELS / name
        try:
            print(f"Trying {url}")
            urllib.request.urlretrieve(url, dest)
            if dest.stat().st_size > 1_000_000:
                print(f"Saved {dest} ({dest.stat().st_size} bytes)")
                return
            print(f"Too small, removing {dest}")
            dest.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed {url}: {exc}")
            dest.unlink(missing_ok=True)

    print("Falling back to local smoke Identity ONNX for Phase 0 session tests")
    create_smoke()


if __name__ == "__main__":
    main()
