#!/usr/bin/env bash
# Gera o executável standalone do DISCBOX para Linux.
# Uso: ./scripts/build_linux.sh
# Precisa ser rodado NO Linux (PyInstaller não faz cross-compile).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install -r requirements-build.txt -q

# Embute o FFmpeg no build se ele já estiver instalado no sistema, pra quem
# baixar o app não precisar instalar separadamente.
if command -v ffmpeg >/dev/null 2>&1; then
    mkdir -p vendor/ffmpeg
    cp "$(command -v ffmpeg)" vendor/ffmpeg/ffmpeg
    echo "FFmpeg encontrado em $(command -v ffmpeg) - será embutido no build."
else
    echo "FFmpeg não encontrado no PATH - o build sairá sem ele embutido."
    echo "Quem for usar o app vai precisar instalar o FFmpeg separadamente."
    echo "(instale com o gerenciador de pacotes da sua distro, ex: sudo apt install ffmpeg)"
    echo "e rode este script de novo pra embutir."
fi

./.venv/bin/python -m PyInstaller discbox.spec --noconfirm --clean

echo ""
echo "Pronto! Executável em: dist/DISCBOX"
