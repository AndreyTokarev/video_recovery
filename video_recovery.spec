# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows GUI binary (onedir)."""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)
bin_dir = root / "bin"

datas = []
binaries = []
if bin_dir.is_dir():
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        src = bin_dir / name
        if src.is_file():
            binaries.append((str(src), "."))

a = Analysis(
    ["scripts/run_gui.py"],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
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
    name="VideoRecovery",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="VideoRecovery",
)
