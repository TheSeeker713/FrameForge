# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FrameForge portable build

import sys
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
    "frameforge.gui.app",
    "frameforge.db.repository",
    "frameforge.queue.worker",
    "frameforge.download.ytdlp",
    "frameforge.download.bulk_import",
    "frameforge.download.handler",
    "frameforge.upscale.pipeline",
    "frameforge.upscale.handler",
    "frameforge.pipeline",
    "customtkinter",
    "onnxruntime",
]

tmp_ret = collect_all("customtkinter")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
