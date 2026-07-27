"""Motor de download de áudio via yt-dlp, com conversão pelo FFmpeg."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from yt_dlp import YoutubeDL

# Formatos suportados: bitrate (kbps) se aplicável, ou None para lossless.
SUPPORTED_FORMATS = {
    "mp3": 320,
    "m4a": 256,
    "opus": 192,
    "flac": None,
    "wav": None,
}

# O YouTube às vezes bloqueia o cliente "web" padrão com um desafio anti-bot
# ("Sign in to confirm you're not a bot"), mas os clientes alternativos
# (apps mobile/TV) costumam continuar servindo áudio normalmente.
_FALLBACK_PLAYER_CLIENTS = ["android", "ios", "tv", "web_safari"]


class DownloadError(Exception):
    """Falha ao baixar ou converter o áudio de uma faixa."""


def _bundled_ffmpeg_dir() -> Path | None:
    """Pasta do FFmpeg empacotado junto do executável (build standalone).

    Um build feito com PyInstaller pode carregar um binário do FFmpeg dentro
    de uma pasta `ffmpeg/` ao lado do executável (ver discbox.spec), pra
    quem baixa o app não precisar instalar o FFmpeg à parte. `sys._MEIPASS`
    é a pasta temporária onde o PyInstaller extrai os dados em modo onefile;
    em modo onedir é a própria pasta do executável.
    """
    if not getattr(sys, "frozen", False):
        return None
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidate = base / "ffmpeg" / name
    return candidate.parent if candidate.exists() else None


def ffmpeg_available() -> bool:
    return _bundled_ffmpeg_dir() is not None or shutil.which("ffmpeg") is not None


def _ffmpeg_install_hint() -> str:
    if sys.platform == "win32":
        return "Instale-o com: winget install --id Gyan.FFmpeg -e (ou baixe em ffmpeg.org)."
    if sys.platform == "darwin":
        return "Instale-o com: brew install ffmpeg (ou baixe em ffmpeg.org)."
    return "Instale-o com o gerenciador de pacotes da sua distro, ex: sudo apt install ffmpeg."


def _extract_final_path(info: dict) -> Path | None:
    """Caminho final real do arquivo, direto do retorno do yt-dlp.

    Antes disso o código *adivinhava* o nome do arquivo (a partir do
    template) e ficava checando se ele já existia no disco — o que dava
    falso negativo: em alguns PCs Windows o antivírus prende um lock no mp3
    recém-criado por uma fração de segundo pra escanear, então a checagem
    dizia "não existe" mesmo com o download 100% concluído. Usar o caminho
    que o próprio yt-dlp reporta ter escrito elimina essa corrida.
    """
    requested = info.get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        return Path(requested[0]["filepath"])
    if info.get("filepath"):
        return Path(info["filepath"])
    return None


class _YtdlpLog:
    """Captura o último erro real do yt-dlp.

    Com `ignoreerrors=True` uma falha não levanta exceção, então sem isso a
    única forma de saber *por que* nenhum arquivo foi gerado (bloqueio
    anti-bot, vídeo indisponível, formato ausente...) seria adivinhar.
    """

    def __init__(self) -> None:
        self.last_error: str | None = None

    def debug(self, msg: str) -> None:
        pass

    info = debug

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        self.last_error = msg


class Downloader:
    """Baixa o áudio de uma URL do YouTube e converte para o formato configurado."""

    def __init__(self, audio_format: str = "mp3", audio_quality: str = "320") -> None:
        if audio_format not in SUPPORTED_FORMATS:
            raise ValueError(f"Formato de áudio não suportado: {audio_format!r}")
        self.audio_format = audio_format
        self.audio_quality = audio_quality

    def download(self, video_url: str, destination: Path) -> Path:
        """Baixa `video_url` e salva como `destination` (extensão é ajustada
        automaticamente para o formato configurado). Retorna o caminho final.

        Tenta primeiro o cliente padrão do YouTube; se nenhum arquivo for
        gerado (ex: desafio anti-bot bloqueando o cliente "web"), tenta de
        novo com clientes alternativos (android/ios/tv), que normalmente não
        são bloqueados.
        """
        if not ffmpeg_available():
            raise DownloadError(f"FFmpeg não encontrado no PATH. {_ffmpeg_install_hint()}")

        base = destination.with_suffix("")

        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": self.audio_format}
        if SUPPORTED_FORMATS[self.audio_format] is not None:
            postprocessor["preferredquality"] = self.audio_quality

        base_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(base) + ".%(ext)s",
            "postprocessors": [postprocessor],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "retries": 5,
            "socket_timeout": 15,
        }
        ffmpeg_dir = _bundled_ffmpeg_dir()
        if ffmpeg_dir:
            base_opts["ffmpeg_location"] = str(ffmpeg_dir)
        fallback_opts = {
            **base_opts,
            "extractor_args": {"youtube": {"player_client": _FALLBACK_PLAYER_CLIENTS}},
        }

        last_error: str | None = None
        for opts in (base_opts, fallback_opts):
            ytlog = _YtdlpLog()
            try:
                with YoutubeDL({**opts, "logger": ytlog}) as ydl:
                    info = ydl.extract_info(video_url, download=True)
            except Exception as e:
                last_error = str(e)
                continue

            last_error = ytlog.last_error
            final_path = _extract_final_path(info) if info else None
            if final_path and final_path.exists():
                return final_path

        reason = f": {last_error}" if last_error else " (nenhum motivo reportado pelo yt-dlp)"
        raise DownloadError(f"Não foi possível baixar o áudio de {video_url}{reason}")
