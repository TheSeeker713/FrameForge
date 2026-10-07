"""Download Real-ESRGAN ONNX if possible; always ensure a loadable ONNX exists."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

from create_smoke_onnx import main as create_smoke

# Float Real-ESRGAN x4plus, NCHW 128 -> 512. Sidecar weights ship in the same zip.
MODEL_ZIP = (
    "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/"
    "qai-hub-models/models/real_esrgan_x4plus/releases/v0.64.0/"
    "real_esrgan_x4plus-onnx-float.zip"
)


def _models_dir() -> Path:
    from frameforge.paths import models_dir

    folder = models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _installed(folder: Path) -> bool:
    onnx = folder / "RealESRGAN_x4plus.onnx"
    data = folder / "real_esrgan_x4plus.data"
    return (
        onnx.is_file()
        and onnx.stat().st_size > 1_000_000
        and data.is_file()
        and data.stat().st_size > 1_000_000
    )


def _install_zip(folder: Path, blob: bytes) -> None:
    archive = zipfile.ZipFile(io.BytesIO(blob))
    onnx_bytes = None
    data_bytes = None
    for name in archive.namelist():
        lower = name.lower()
        if lower.endswith(".onnx"):
            onnx_bytes = archive.read(name)
        elif lower.endswith(".data"):
            data_bytes = archive.read(name)
    if not onnx_bytes or not data_bytes:
        raise RuntimeError("model zip did not contain an ONNX file and a weight sidecar")
    (folder / "RealESRGAN_x4plus.onnx").write_bytes(onnx_bytes)
    (folder / "real_esrgan_x4plus.data").write_bytes(data_bytes)


def main() -> None:
    folder = _models_dir()
    if _installed(folder):
        print(f"Real-ESRGAN already present: {folder / 'RealESRGAN_x4plus.onnx'}")
        return

    dest_zip = folder / "real_esrgan_x4plus.zip"
    try:
        print(f"Trying {MODEL_ZIP}")
        urlretrieve(MODEL_ZIP, dest_zip)
        _install_zip(folder, dest_zip.read_bytes())
        dest_zip.unlink(missing_ok=True)
        if _installed(folder):
            onnx = folder / "RealESRGAN_x4plus.onnx"
            print(f"Saved {onnx} ({onnx.stat().st_size} bytes)")
            return
        print("Downloaded archive was incomplete")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed {MODEL_ZIP}: {exc}")
        dest_zip.unlink(missing_ok=True)

    print("Falling back to local smoke Identity ONNX for Phase 0 session tests")
    create_smoke()


if __name__ == "__main__":
    main()
