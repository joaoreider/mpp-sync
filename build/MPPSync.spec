# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
project_root = os.path.abspath(os.path.join(SPECPATH, ".."))

mpxj_datas, mpxj_binaries, mpxj_hiddenimports = collect_all("mpxj")
pystray_datas, pystray_binaries, pystray_hiddenimports = collect_all("pystray")
pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all("PIL")

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=mpxj_binaries + pystray_binaries + pillow_binaries,
    datas=mpxj_datas + pystray_datas + pillow_datas,
    hiddenimports=[
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "jpype",
        "pyodbc",
        "pystray",
        "sqlalchemy",
        "watchdog.events",
        "watchdog.observers",
    ]
    + mpxj_hiddenimports
    + pystray_hiddenimports
    + pillow_hiddenimports,
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
    name="MPPSync",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MPPSync",
)
