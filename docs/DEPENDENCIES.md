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
# curl_cffi==0.13.0 is required for yt-dlp --impersonate (PornHub). Do not
# upgrade curl_cffi alone to 0.16.x while yt-dlp is 2026.07.04.
# GUI (v0.5): flet==0.86.5 is a project dependency
pip install onnx   # used to generate local smoke ONNX if Real-ESRGAN download unavailable
python .\scripts\create_smoke_onnx.py
# Optional when network policy allows Real-ESRGAN weights:
# python .\scripts\download_models.py
```

## Pip packages (venv)

| Package | Version |
|---------|---------|
| yt-dlp | 2026.7.4 |
| curl_cffi | 0.13.0 | Required for `--impersonate chrome`. 0.16.x is unsupported with this yt-dlp |
| onnxruntime-directml | 1.24.4 |
| customtkinter | 6.0.0 |
| flet | 0.86.5 | Primary GUI (v0.5); pin used in tests |
| Pillow | 12.3.0 |
| pystray | 0.19.5 |
| psutil | 7.2.2 |
| numpy | 2.5.2 |
| opencv-python-headless | 5.0.0.93 |
| pytest | 9.1.1 |
| pytest-timeout | 2.4.0 |
| pyinstaller | 6.22.0 |
| onnx | 1.22.0 |

## ONNX providers detected

`DmlExecutionProvider`, `CPUExecutionProvider`

## Impersonate (`python -m frameforge --check-env`)

JSON key `impersonation`: `yt_dlp_version`, `curl_cffi_version`, `curl_cffi_supported`, `chrome_available`, `clients`, `selected`. Overall `ok` is false if Chrome is unavailable. See [ADULT_SITES.md](ADULT_SITES.md).

Also: `extractor_count` from yt-dlp’s extractor registry (multi-site surface). See [MULTI_SITE.md](MULTI_SITE.md).

## Models

Phase 0 session smoke model (local Identity ONNX):

`%USERPROFILE%\Downloads\FrameForge\models\frameforge_smoke_identity.onnx`

Real-ESRGAN x4plus ONNX will be fetched in Phase 2 setup when external model download is available (`scripts/download_models.py`).
