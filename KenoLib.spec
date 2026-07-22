# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files('customtkinter')
datas += [('app_icon.ico', '.')]

# reportlab.graphics.barcode/__init__ importă dinamic TOATE backend-urile de
# cod de bare (code39, code93, code128, ...) prin _reset(), dar PyInstaller
# vede doar code128 (singurul importat explicit) -> lipsesc restul, iar
# aplicația crapă la pornire cu "No module named ...barcode.code93".
# collect_submodules le include pe toate.
hiddenimports = collect_submodules('reportlab.graphics.barcode')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'tensorboard'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KenoLib',
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
    icon='app_icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KenoLib',
)
