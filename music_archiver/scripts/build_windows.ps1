# Gera o executável standalone do DISCBOX para Windows.
# Uso: .\scripts\build_windows.ps1
# Precisa ser rodado NO Windows (PyInstaller não faz cross-compile).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt -q

# Embute o FFmpeg no build se ele já estiver instalado no sistema, pra quem
# baixar o app não precisar instalar separadamente.
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
    New-Item -ItemType Directory -Force -Path "vendor\ffmpeg" | Out-Null
    Copy-Item $ffmpegCmd.Source "vendor\ffmpeg\ffmpeg.exe" -Force
    Write-Host "FFmpeg encontrado em $($ffmpegCmd.Source) - será embutido no build."
} else {
    Write-Host "FFmpeg não encontrado no PATH - o build sairá sem ele embutido."
    Write-Host "Quem for usar o app vai precisar instalar o FFmpeg separadamente."
    Write-Host "(instale com: winget install --id Gyan.FFmpeg -e) e rode este script de novo pra embutir."
}

& .\.venv\Scripts\python.exe -m PyInstaller discbox.spec --noconfirm --clean

Write-Host ""
Write-Host "Pronto! Executável em: dist\DISCBOX.exe"
