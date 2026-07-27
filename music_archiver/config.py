"""Configurações centrais do DISCBOX.

Não é necessária nenhuma credencial da Spotify: os metadados são lidos das
páginas públicas de embed (ver spotify_client.py), e o áudio vem do YouTube
via yt-dlp.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Rodando a partir do código-fonte, __file__ é a pasta do projeto. Empacotado
# (PyInstaller), o executável roda de uma pasta temporária que é apagada ao
# fechar o app — nada que precise sobreviver entre execuções (configurações
# salvas, pasta padrão de downloads) pode morar lá.
_FROZEN = getattr(sys, "frozen", False)
_SCRIPT_DIR = Path(__file__).resolve().parent


def _user_data_dir() -> Path:
    """Pasta de dados do app no local padrão de cada sistema operacional."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "DISCBOX"


BASE_DIR = _user_data_dir() if _FROZEN else _SCRIPT_DIR
BASE_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_DOWNLOAD_DIR = (Path.home() / "Music" / "DISCBOX") if _FROZEN else (_SCRIPT_DIR / "downloads")

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR") or _DEFAULT_DOWNLOAD_DIR)
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "mp3")
AUDIO_QUALITY = os.getenv("AUDIO_QUALITY", "320")

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Última pasta/formato/qualidade escolhidos na GUI, pra não voltar ao padrão
# toda vez que o app abre.
GUI_SETTINGS_FILE = BASE_DIR / ".gui_settings.json"


def load_gui_settings() -> dict:
    try:
        with open(GUI_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_gui_settings(settings: dict) -> None:
    try:
        with open(GUI_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass
