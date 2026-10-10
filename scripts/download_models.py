"""Download Real-ESRGAN ONNX into the chosen FrameForge models folder."""

from __future__ import annotations

from frameforge.upscale.weights import install_realesrgan, realesrgan_installed


def main() -> None:
    from frameforge.paths import models_dir

    folder = models_dir()
    if realesrgan_installed(folder):
        print(f"Real-ESRGAN already present: {folder / 'RealESRGAN_x4plus.onnx'}")
        return
    try:
        dest = install_realesrgan(folder)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not install Real-ESRGAN: {exc}")
        print("Falling back to local smoke Identity ONNX for session tests")
        from create_smoke_onnx import main as create_smoke

        create_smoke()
        return
    print(f"Saved {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
