"""Download Real-ESRGAN weights into the chosen FrameForge models folder.

Smoke Identity and the tiny 2x resize file are not this model. The Windows
Downloads tree is never created from here.
"""

from __future__ import annotations

import logging
import threading
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

ONNX_NAME = "RealESRGAN_x4plus.onnx"
DATA_NAME = "real_esrgan_x4plus.data"
MIN_BYTES = 1_000_000
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MODEL_ZIP = (
    "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/"
    "qai-hub-models/models/real_esrgan_x4plus/releases/v0.64.0/"
    "real_esrgan_x4plus-onnx-float.zip"
)

StatusCb = Callable[..., None]

_LOCK = threading.Lock()
_RUNNING = False


def realesrgan_installed(folder: Path | None = None, *, min_bytes: int = MIN_BYTES) -> bool:
    """True when both the ONNX graph and the weight sidecar are present and large enough."""
    root = _folder(folder)
    onnx = root / ONNX_NAME
    data = root / DATA_NAME
    try:
        return (
            onnx.is_file()
            and onnx.stat().st_size > min_bytes
            and data.is_file()
            and data.stat().st_size > min_bytes
        )
    except OSError:
        return False


def install_realesrgan(
    folder: Path | None = None,
    *,
    min_bytes: int = MIN_BYTES,
    url: str = MODEL_ZIP,
    opener=None,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download and install the weights. Blocking. Raises if the folder must not be created."""
    from frameforge.paths import ensure_dir, may_create

    root = _folder(folder)
    if realesrgan_installed(root, min_bytes=min_bytes):
        return root / ONNX_NAME
    if not may_create(root):
        raise OSError(f"Refusing to create {root}")
    ensure_dir(root)
    if not root.is_dir():
        raise OSError(f"Could not create {root}")

    partial = root / "real_esrgan_x4plus.zip.partial"
    fetch = opener or urlopen
    try:
        request = Request(url, headers={"User-Agent": "FrameForge"})
        with fetch(request, timeout=120) as response, partial.open("wb") as handle:
            total_header = response.headers.get("Content-Length") if response.headers else None
            total = int(total_header) if total_header and str(total_header).isdigit() else None
            done = 0
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        _install_zip(root, partial, min_bytes=min_bytes)
    finally:
        partial.unlink(missing_ok=True)
    if not realesrgan_installed(root, min_bytes=min_bytes):
        raise RuntimeError("Downloaded archive did not contain the Real-ESRGAN weights")
    return root / ONNX_NAME


def start_realesrgan_install(
    on_status: StatusCb | None = None,
    on_ready: Callable[[], None] | None = None,
) -> bool:
    """Start one background download. False when the weights are already present or a fetch is running."""
    global _RUNNING
    if realesrgan_installed():
        return False
    with _LOCK:
        if _RUNNING:
            return False
        _RUNNING = True

    def work() -> None:
        global _RUNNING
        try:
            _notify(on_status, "Downloading the upscale model…", done=False)
            install_realesrgan()
            if on_ready is not None:
                try:
                    on_ready()
                except Exception:  # noqa: BLE001
                    log.exception("Upscale model reload failed")
            _notify(on_status, "Upscale model installed.", done=True)
        except Exception as exc:  # noqa: BLE001
            log.exception("Upscale model download failed")
            _notify(
                on_status,
                f"Could not download the upscale model. {exc}",
                done=True,
            )
        finally:
            with _LOCK:
                _RUNNING = False

    threading.Thread(target=work, name="realesrgan-install", daemon=True).start()
    return True


def _folder(folder: Path | None) -> Path:
    if folder is not None:
        return Path(folder)
    from frameforge.paths import models_dir

    return models_dir()


def _notify(callback: StatusCb | None, message: str, *, done: bool) -> None:
    if callback is None:
        return
    try:
        callback(message, done=done)
    except TypeError:
        callback(message)


def _install_zip(folder: Path, archive_path: Path, *, min_bytes: int) -> None:
    onnx_bytes: bytes | None = None
    data_bytes: bytes | None = None
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name.lower()
            if info.file_size > MAX_MEMBER_BYTES:
                raise RuntimeError("model zip member is too large")
            if name.endswith(".onnx") and onnx_bytes is None:
                onnx_bytes = _read_member(archive, info)
            elif name.endswith(".data") and data_bytes is None:
                data_bytes = _read_member(archive, info)
    if not onnx_bytes or not data_bytes:
        raise RuntimeError("model zip did not contain an ONNX file and a weight sidecar")
    if len(onnx_bytes) <= min_bytes or len(data_bytes) <= min_bytes:
        raise RuntimeError("model zip was incomplete")
    _write_atomic(folder / ONNX_NAME, onnx_bytes)
    _write_atomic(folder / DATA_NAME, data_bytes)


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    with archive.open(info) as handle:
        blob = handle.read(MAX_MEMBER_BYTES + 1)
    if len(blob) > MAX_MEMBER_BYTES:
        raise RuntimeError("model zip member is too large")
    return blob


def _write_atomic(dest: Path, blob: bytes) -> None:
    temporary = dest.with_suffix(dest.suffix + ".partial")
    temporary.write_bytes(blob)
    temporary.replace(dest)
