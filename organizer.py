"""Organização dos arquivos baixados em pastas e nomes de arquivo seguros.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

_RESERVED_CHARS = '<>:"/\\|?*'
_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def sanitize_filename(name: str) -> str:
    """Sanitiza uma string para uso seguro como nome de arquivo/pasta."""
    normalized = unicodedata.normalize("NFC", name)
    cleaned = "".join(
        ch for ch in normalized if ch not in _RESERVED_CHARS and unicodedata.category(ch) != "Cc"
    )
    cleaned = " ".join(cleaned.split())  # colapsa espaços múltiplos
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return "Unknown"
    if cleaned.split(".")[0].upper() in _RESERVED_DEVICE_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def cap_filename(name: str, max_bytes: int = 250) -> str:
    """Limita o nome completo (com extensão) a um tamanho válido em qualquer SO."""
    if len(name.encode("utf-8")) <= max_bytes:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not ext or len(ext) > 10 or " " in ext:
        stem, ext = name, ""
    suffix = f".{ext}" if ext else ""
    budget = max(1, max_bytes - len(suffix.encode("utf-8")))
    stem = stem.encode("utf-8")[:budget].decode("utf-8", "ignore").rstrip(" .")
    return f"{stem}{suffix}" if stem else f"file{suffix}"


class Organizer:
    """Resolve o caminho final de uma faixa dentro da pasta de downloads."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def container_folder(self, container_name: str | None) -> Path:
        """Pasta de destino para uma playlist/álbum (ou a raiz, para faixa avulsa)."""
        if not container_name:
            folder = self.base_dir
        else:
            folder = self.base_dir / sanitize_filename(container_name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def track_path(
        self, folder: Path, track: dict, extension: str, track_number: int | None = None
    ) -> Path:
        """Caminho completo do arquivo de uma faixa, com nome sanitizado."""
        title = sanitize_filename(track["name"])
        artist = sanitize_filename(track["artist"])
        if track_number:
            filename = f"{track_number:02d}. {title} - {artist}.{extension}"
        else:
            filename = f"{title} - {artist}.{extension}"
        filename = cap_filename(filename)
        return folder / filename
