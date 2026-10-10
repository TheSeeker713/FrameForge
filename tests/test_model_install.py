"""Upscale weights install into the chosen models folder, never Windows Downloads."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

from frameforge.paths import choose_download_location, models_dir, profile_frameforge_root
from frameforge.upscale.weights import install_realesrgan, realesrgan_installed


def _zip_bytes(onnx: bytes, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nested/RealESRGAN_x4plus.onnx", onnx)
        archive.writestr("nested/real_esrgan_x4plus.data", data)
    return buffer.getvalue()


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, size: int = -1) -> bytes:
        return self._payload.read(size)

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _isolate(monkeypatch, tmp_path: Path) -> Path:
    profile = tmp_path / "profile"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("FRAMEFORGE_ROOT", raising=False)
    monkeypatch.setattr("frameforge.paths._userprofile_redirected", lambda: False)
    choose_download_location(tmp_path / "Videos")
    return profile


def test_install_writes_weights_under_the_chosen_models_folder(monkeypatch, tmp_path: Path):
    profile = _isolate(monkeypatch, tmp_path)
    payload = _zip_bytes(b"o" * 32, b"d" * 32)

    def opener(_request, timeout=0):  # noqa: ANN001
        assert timeout
        return _Response(payload)

    dest = install_realesrgan(min_bytes=8, opener=opener)
    assert dest == models_dir() / "RealESRGAN_x4plus.onnx"
    assert dest.is_file()
    assert (models_dir() / "real_esrgan_x4plus.data").stat().st_size == 32
    assert realesrgan_installed(min_bytes=8)
    assert not realesrgan_installed(min_bytes=10_000)
    assert not (models_dir() / "real_esrgan_x4plus.zip.partial").exists()
    assert not profile_frameforge_root().exists()
    assert not (profile / "Downloads").exists()


def test_install_refuses_the_windows_downloads_tree(monkeypatch, tmp_path: Path):
    blocked = tmp_path / "Downloads" / "FrameForge" / "models"
    monkeypatch.setattr("frameforge.paths.may_create", lambda _path: False)
    try:
        install_realesrgan(blocked, min_bytes=8, opener=lambda *_a, **_k: None)
    except OSError as exc:
        assert "Refusing" in str(exc)
    else:
        raise AssertionError("install created a folder that is not allowed")
    assert not blocked.exists()


def test_dev_model_scripts_use_the_chosen_folder(monkeypatch, tmp_path: Path):
    profile = _isolate(monkeypatch, tmp_path)
    root = Path(__file__).resolve().parents[1]
    for name in ("create_x2_onnx.py", "create_smoke_onnx.py"):
        text = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "USERPROFILE" not in text
        assert "Downloads" not in text
    spec = importlib.util.spec_from_file_location(
        "create_x2_onnx",
        root / "scripts" / "create_x2_onnx.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dest = module.main()
    assert dest == tmp_path / "Videos" / "FrameForge" / "models" / "frameforge_x2_resize.onnx"
    assert dest.is_file()
    assert not profile_frameforge_root().exists()
