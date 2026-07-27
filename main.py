"""Ponto de entrada do DISCBOX: baixa faixas/álbuns/playlists da Spotify via YouTube.

Uso:
    python main.py <url-da-spotify> [--format mp3] [--quality 320] [--out PASTA]
    python main.py --gui
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import config
from downloader import DownloadError, Downloader
from duplicate_checker import DuplicateChecker
from metadata_handler import MetadataHandler
from organizer import Organizer
from spotify_client import SpotifyClient, SpotifyClientError, detect_url_type
from youtube_search import YouTubeSearcher

ProgressCallback = Callable[[str], None]
TracksCallback = Callable[[list[dict]], None]
TrackStatusCallback = Callable[[int, str], None]


def fetch_tracks(url: str) -> tuple[str, str | None, list[dict]]:
    """Só lê os metadados (sem baixar nada). Retorna (tipo, nome_do_container, faixas).

    `tipo` é "track", "album" ou "playlist". `nome_do_container` é o nome do
    álbum/playlist (None para faixa avulsa) — usado como nome da pasta e
    exibido na prévia antes do usuário confirmar o download.
    """
    spotify = SpotifyClient()
    content_type, _ = detect_url_type(url)

    if content_type == "track":
        return content_type, None, [spotify.get_track(url)]

    container_name = spotify.get_container_name(url)
    tracks = spotify.get_album_tracks(url) if content_type == "album" else spotify.get_playlist_tracks(url)
    return content_type, container_name, tracks


def download_tracks(
    tracks: list[dict],
    container_name: str | None,
    output_dir: Path | None = None,
    audio_format: str | None = None,
    audio_quality: str | None = None,
    progress_cb: ProgressCallback = print,
    on_track_status: TrackStatusCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    selected_indices: set[int] | None = None,
) -> tuple[int, int]:
    """Baixa uma lista de faixas já obtida via `fetch_tracks`. Retorna (sucessos, falhas).

    `on_track_status` (opcional) é chamado a cada mudança de status de uma
    faixa específica (por índice), com um dos valores: "baixando", "já
    existe", "não encontrado", "falhou", "concluído", "cancelado".

    `is_cancelled` (opcional) é checado antes de cada faixa; se retornar
    True, as faixas restantes ficam com status "cancelado" e a função
    retorna imediatamente com o que já tinha sido feito até ali.

    `selected_indices` (opcional) restringe o download a um subconjunto das
    faixas (por índice em `tracks`) — as demais são ignoradas por completo
    (nem contam pra `ok`/`failed`, nem disparam `on_track_status`). O número
    da faixa gravado na tag/nome do arquivo continua sendo a posição real
    dela no álbum/playlist, não a posição entre as selecionadas.
    """
    output_dir = Path(output_dir) if output_dir else config.DOWNLOAD_DIR
    audio_format = audio_format or config.AUDIO_FORMAT
    audio_quality = audio_quality or config.AUDIO_QUALITY

    searcher = YouTubeSearcher()
    downloader = Downloader(audio_format=audio_format, audio_quality=audio_quality)
    organizer = Organizer(output_dir)
    dup_checker = DuplicateChecker()
    metadata = MetadataHandler()

    folder = organizer.container_folder(container_name)
    track_numbers = list(range(1, len(tracks) + 1)) if container_name else [None] * len(tracks)

    ok, failed = 0, 0
    for index, (track, track_number) in enumerate(zip(tracks, track_numbers)):
        if selected_indices is not None and index not in selected_indices:
            continue

        if is_cancelled and is_cancelled():
            progress_cb("Download cancelado.")
            if on_track_status:
                for remaining in range(index, len(tracks)):
                    if selected_indices is None or remaining in selected_indices:
                        on_track_status(remaining, "cancelado")
            break

        label = f"{track['artist']} - {track['name']}"
        filepath = organizer.track_path(folder, track, audio_format, track_number)

        if dup_checker.is_duplicate(filepath):
            progress_cb(f"[já existe] {label}")
            if on_track_status:
                on_track_status(index, "já existe")
            ok += 1
            continue

        if on_track_status:
            on_track_status(index, "baixando")

        video_url = searcher.search(track)
        if not video_url:
            progress_cb(f"[não encontrado no YouTube] {label}")
            if on_track_status:
                on_track_status(index, "não encontrado")
            failed += 1
            continue

        try:
            downloaded_path = downloader.download(video_url, filepath)
            metadata.apply(downloaded_path, track, track_number)
        except DownloadError as e:
            progress_cb(f"[falha] {label}: {e}")
            if on_track_status:
                on_track_status(index, "falhou")
            failed += 1
            continue

        progress_cb(f"[ok] {label}")
        if on_track_status:
            on_track_status(index, "concluído")
        ok += 1

    return ok, failed


def download_from_url(
    url: str,
    output_dir: Path | None = None,
    audio_format: str | None = None,
    audio_quality: str | None = None,
    progress_cb: ProgressCallback = print,
    on_tracks: TracksCallback | None = None,
    on_track_status: TrackStatusCallback | None = None,
) -> tuple[int, int]:
    """Busca os metadados e baixa em uma única chamada (usado pela CLI).

    `on_tracks` (opcional) é chamado uma vez com a lista completa de faixas
    assim que os metadados são lidos, antes dos downloads começarem.
    """
    _, container_name, tracks = fetch_tracks(url)
    if container_name:
        progress_cb(f"{container_name}: {len(tracks)} faixa(s) encontrada(s)")
    if on_tracks:
        on_tracks(tracks)
    return download_tracks(
        tracks,
        container_name,
        output_dir=output_dir,
        audio_format=audio_format,
        audio_quality=audio_quality,
        progress_cb=progress_cb,
        on_track_status=on_track_status,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DISCBOX: baixa faixas/álbuns/playlists da Spotify via YouTube.")
    parser.add_argument("url", nargs="?", help="URL da Spotify (faixa, álbum ou playlist)")
    parser.add_argument("--format", dest="audio_format", default=None, help="Formato de áudio (mp3, m4a, flac, opus, wav)")
    parser.add_argument("--quality", dest="audio_quality", default=None, help="Qualidade em kbps (para mp3/m4a/opus)")
    parser.add_argument("--out", dest="output_dir", default=None, help="Pasta de destino dos downloads")
    parser.add_argument("--gui", action="store_true", help="Abre a interface gráfica")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    if args.gui:
        from gui import main as gui_main

        gui_main()
        return

    if not args.url:
        print("Uso: python main.py <url-da-spotify> [--format mp3] [--quality 320] [--out PASTA]")
        print("     python main.py --gui")
        sys.exit(1)

    try:
        ok, failed = download_from_url(
            args.url,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            audio_format=args.audio_format,
            audio_quality=args.audio_quality,
        )
    except (SpotifyClientError, ValueError) as e:
        print(f"Erro: {e}")
        sys.exit(1)

    print(f"\nConcluído: {ok} ok, {failed} falha(s).")
    sys.exit(1 if failed and not ok else 0)


if __name__ == "__main__":
    main()
