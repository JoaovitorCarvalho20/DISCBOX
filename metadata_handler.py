"""Escrita de tags de metadados e capa de álbum nos arquivos baixados.

Cada container de áudio usa um sistema de tags diferente (ID3 para mp3,
átomos iTunes para m4a, Vorbis comments para flac). mp3 é gravado como
ID3v2.3 + UTF-16 (em vez do padrão v2.4/UTF-8 do mutagen) por ser o menor
denominador comum entendido por iTunes antigo, Windows Media Player, rádios
de carro e players Android — nenhum dos quais lê de forma confiável frames
APIC em v2.4.
"""

from __future__ import annotations

from pathlib import Path

import requests


def _fetch_cover_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except requests.RequestException:
        pass
    return None


def _detect_image_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _write_mp3(filepath: Path, tags: dict, cover_bytes: bytes | None) -> None:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import APIC, ID3

    audio = EasyID3(filepath)
    audio["title"] = tags["name"]
    audio["artist"] = tags["artist"]
    audio["album"] = tags.get("album") or ""
    if tags.get("release_date"):
        audio["date"] = tags["release_date"]
    if tags.get("track_number"):
        audio["tracknumber"] = str(tags["track_number"])
    audio.save(v2_version=3)

    if cover_bytes:
        id3 = ID3(filepath)
        id3.add(
            APIC(
                encoding=1,
                mime=_detect_image_mime(cover_bytes),
                type=3,
                desc="Cover",
                data=cover_bytes,
            )
        )
        id3.update_to_v23()
        id3.save(v2_version=3)


def _write_m4a(filepath: Path, tags: dict, cover_bytes: bytes | None) -> None:
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(filepath)
    audio["\xa9nam"] = tags["name"]
    audio["\xa9ART"] = tags["artist"]
    audio["\xa9alb"] = tags.get("album") or ""
    if tags.get("release_date"):
        audio["\xa9day"] = tags["release_date"]
    if tags.get("track_number"):
        audio["trkn"] = [(int(tags["track_number"]), 0)]
    if cover_bytes:
        fmt = MP4Cover.FORMAT_PNG if _detect_image_mime(cover_bytes) == "image/png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
    audio.save()


def _write_flac(filepath: Path, tags: dict, cover_bytes: bytes | None) -> None:
    from mutagen.flac import FLAC, Picture

    audio = FLAC(filepath)
    audio["title"] = tags["name"]
    audio["artist"] = tags["artist"]
    audio["album"] = tags.get("album") or ""
    if tags.get("release_date"):
        audio["date"] = tags["release_date"]
    if tags.get("track_number"):
        audio["tracknumber"] = str(tags["track_number"])
    if cover_bytes:
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = _detect_image_mime(cover_bytes)
        pic.desc = "Cover"
        pic.data = cover_bytes
        audio.add_picture(pic)
    audio.save()


_WRITERS = {
    ".mp3": _write_mp3,
    ".m4a": _write_m4a,
    ".flac": _write_flac,
}


class MetadataHandler:
    """Aplica metadados de uma faixa (dict vindo do SpotifyClient) a um arquivo local."""

    def apply(self, filepath: Path, track: dict, track_number: int | None = None) -> None:
        """Grava título/artista/álbum/data/faixa + capa. Formatos sem writer
        (opus, wav) são ignorados silenciosamente — não têm um padrão de tag
        universal que justifique a dependência extra."""
        writer = _WRITERS.get(filepath.suffix.lower())
        if writer is None:
            return

        tags = {**track, "track_number": track_number}
        cover_bytes = _fetch_cover_bytes(track.get("cover_url"))
        writer(filepath, tags, cover_bytes)
