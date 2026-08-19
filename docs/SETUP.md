# Setup

## Prerequisites

- Windows 11
- Python 3.12+
- FFmpeg (full) on PATH
- aria2c on PATH
- Network for first-time dependency and model download

## Bootstrap

```powershell
cd D:\_Dev\Projects\FrameForge
.\scripts\bootstrap_venv.ps1
.\.venv\Scripts\Activate.ps1
.\scripts\download_models.ps1
# If models\ is empty, the GUI will try to write smoke Identity ONNX (not Real-ESRGAN):
# python .\scripts\create_smoke_onnx.py
python -m frameforge --check-env
# JSON impersonation.ok / chrome_available must be true for PornHub (curl_cffi 0.13.0)
pytest -q
```

## Output directory

Created automatically:

`%USERPROFILE%\Downloads\FrameForge\`

## Notes

After initial setup the app is designed to work offline for local upscaling of already-downloaded media (downloads still need network).
