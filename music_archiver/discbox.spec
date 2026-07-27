# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o DISCBOX.

Gera um executável standalone (onefile) que não precisa de Python instalado
na máquina de quem for usar. Se houver um binário do FFmpeg em
vendor/ffmpeg/ (ver scripts/build_*), ele é embutido no pacote — assim quem
baixa o app não precisa instalar o FFmpeg à parte. Sem isso, o app ainda
funciona, mas passa a exigir o FFmpeg no PATH do sistema.

Uso: pyinstaller discbox.spec
"""

import sys
from pathlib import Path

PROJECT_DIR = Path(SPECPATH)
VENDOR_FFMPEG = PROJECT_DIR / "vendor" / "ffmpeg"

datas = [(str(PROJECT_DIR / "assets"), "assets")]

_ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
_ffmpeg_bin = VENDOR_FFMPEG / _ffmpeg_name
if _ffmpeg_bin.exists():
    datas.append((str(_ffmpeg_bin), "ffmpeg"))

if sys.platform == "win32":
    _icon = str(PROJECT_DIR / "assets" / "icon.ico")
elif sys.platform == "darwin":
    _candidate = PROJECT_DIR / "assets" / "icon.icns"
    _icon = str(_candidate) if _candidate.exists() else None
else:
    _icon = None

a = Analysis(
    ["discbox_app.py"],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DISCBOX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# macOS espera um bundle .app, não um binário solto.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="DISCBOX.app",
        icon=_icon,
        bundle_identifier="com.discbox.musicdownloader",
        info_plist={"NSHighResolutionCapable": True},
    )
