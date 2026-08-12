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
python -m frameforge --check-env
pytest -q
```

## Output directory

Created automatically:

`%USERPROFILE%\Downloads\FrameForge\`

## Notes

After initial setup the app is designed to work offline for local upscaling of already-downloaded media (downloads still need network).
