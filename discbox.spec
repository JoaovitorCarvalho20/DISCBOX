# -*- mode: python ; coding: utf-8 -*-
# Config do PyInstaller pra empacotar o DISCBOX num executável único.
# Rodado pelos scripts em scripts/build_*.{ps1,sh} — não roda direto.

import sys
from pathlib import Path

block_cipher = None

root = Path(SPECPATH)

# O FFmpeg é copiado para vendor/ffmpeg/ pelos scripts de build (se
# disponível no sistema) e embutido em ffmpeg/ dentro do executável.
# downloader.py procura o binário nesse mesmo caminho relativo em runtime
# (sys._MEIPASS / "ffmpeg").
_ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
_ffmpeg_src = root / "vendor" / "ffmpeg" / _ffmpeg_name
binaries = [(str(_ffmpeg_src), "ffmpeg")] if _ffmpeg_src.exists() else []

# gui.py lê o ícone de assets/icon.svg relativo à própria localização, que
# ao rodar empacotado é a raiz do bundle (_MEIPASS) — por isso a pasta
# assets/ inteira precisa ir junto como dado, não só o .ico do executável.
datas = [(str(root / "assets"), "assets")]

a = Analysis(
    ["discbox_app.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = str(root / "assets" / "icon.ico") if sys.platform == "win32" else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="DISCBOX.app",
        bundle_identifier="com.discbox.app",
    )
