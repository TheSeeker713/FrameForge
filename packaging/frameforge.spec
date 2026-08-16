# -*- mode: python ; coding: utf-8 -*-
# One-folder PyInstaller build for the Flet GUI (stable on Windows).
# One-file is not used: Flet's desktop client is a Flutter tree that
# does not extract reliably from a single exe on this stack.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
ENTRY = SRC / "frameforge" / "__main__.py"

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    "frameforge",
    "frameforge.__main__",
    "frameforge.ui_flet.app",
    "frameforge.ui_flet.bridge",
    "frameforge.gui.app",
    "frameforge.db.repository",
    "frameforge.queue.worker",
    "frameforge.download.ytdlp",
    "frameforge.download.impersonate",
    "frameforge.download.bulk_import",
    "frameforge.download.handler",
    "frameforge.download.cookie_validate",
    "frameforge.upscale.pipeline",
    "frameforge.upscale.handler",
    "frameforge.pipeline",
    "flet",
    "flet_desktop",
    "customtkinter",
    "onnxruntime",
    "rich",
    "curl_cffi",
    "curl_cffi.requests",
]

for pkg in ("flet", "flet_desktop", "customtkinter", "curl_cffi"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# Bundle the already-cached Flet Windows client next to the exe so --gui
# does not depend on a first-run GitHub download when the cache exists.
_flet_client = Path.home() / ".flet" / "client" / "flet-desktop-full-0.86.5" / "flet"
if _flet_client.is_dir() and (_flet_client / "flet.exe").is_file():
    datas.append((str(_flet_client), "flet-client"))

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "pyi_rth_flet_view.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FrameForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FrameForge",
)
