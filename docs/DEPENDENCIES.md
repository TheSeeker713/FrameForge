# Dependencies

Exact versions recorded on the Phase 0 build machine (Windows 11, Python 3.12.10).

## System tools (pre-installed)

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12.10 | `C:\Users\jroba\AppData\Local\Programs\Python\Python312\python.exe` |
| FFmpeg | 8.1.2-full_build (gyan.dev) | On PATH |
| aria2c | 1.37.0 | On PATH |
| Vulkan | vulkaninfo present | Inference uses DirectML/CPU in v1 |

## Project venv install commands

```powershell
cd D:\_Dev\Projects\FrameForge
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pip install onnx   # used to generate local smoke ONNX if Real-ESRGAN download unavailable
python .\scripts\create_smoke_onnx.py
# Optional when network policy allows Real-ESRGAN weights:
# python .\scripts\download_models.py
```

## Pip packages (venv)

| Package | Version |
|---------|---------|
| yt-dlp | 2026.7.4 |
| onnxruntime-directml | 1.24.4 |
| customtkinter | 6.0.0 |
| Pillow | 12.3.0 |
| numpy | 2.5.2 |
| opencv-python-headless | 5.0.0.93 |
| pytest | 9.1.1 |
| pytest-timeout | 2.4.0 |
| pyinstaller | 6.22.0 |
| onnx | 1.22.0 |

## ONNX providers detected

`DmlExecutionProvider`, `CPUExecutionProvider`

## Models

Phase 0 session smoke model (local Identity ONNX):

`%USERPROFILE%\Downloads\FrameForge\models\frameforge_smoke_identity.onnx`

Real-ESRGAN x4plus ONNX will be fetched in Phase 2 setup when external model download is available (`scripts/download_models.py`).
