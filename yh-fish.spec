# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller：onedir；目录名由环境变量 ``YH_FISH_EXE_BASENAME`` 决定；图标 ``release/app-icon.ico``。"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
_repo = Path(SPEC).parent.resolve()
_exe_base = os.environ.get("YH_FISH_EXE_BASENAME", "yh-fish")
_ico = _repo / "release" / "app-icon.ico"
_exe_extra = {}
if _ico.is_file():
    _exe_extra["icon"] = str(_ico)
_py = _repo / "python"

_datas_w, _bins_w, _hidden_w = collect_all("webview")

a = Analysis(
    [str(_py / "main.py")],
    pathex=[str(_repo), str(_py)],
    binaries=_bins_w,
    datas=[(str(_py / "images"), "python/images"), *_datas_w],
    hiddenimports=_hidden_w,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_exe_base,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **_exe_extra,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=_exe_base,
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
)
