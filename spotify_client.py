"""Leitura de metadados públicos da Spotify via páginas de embed.

A página `open.spotify.com/embed/{tipo}/{id}` — a mesma que a Spotify usa
pra gerar o player incorporado em sites de terceiros — carrega um bloco
JSON (`__NEXT_DATA__`) com título, artistas, álbum, capa e duração das
faixas. Como é uma página pública, dá pra ler tudo isso sem precisar de
Client ID/Secret nem de login.
"""

from __future__ import annotations

import concurrent.futures
import html as _html
import json
import re

import requests

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_EMBED_URLS = {
    "playlist": "https://open.spotify.com/embed/playlist/{id}",
    "album": "https://open.spotify.com/embed/album/{id}",
    "track": "https://open.spotify.com/embed/track/{id}",
}
_TRACK_PAGE_URL = "https://open.spotify.com/track/{id}"

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>')

# Aceita URL canônica, URL com prefixo de idioma (/intl-xx/) e URI (spotify:tipo:id).
_SPOTIFY_ID_RE = re.compile(
    r"(?:https?://open\.spotify\.com/(?:intl-[a-z]{2,}/)?|spotify:)"
    r"(?P<type>playlist|track|album)[/:](?P<id>[a-zA-Z0-9]+)"
)

# Página de compartilhamento social da Spotify inclui `og:description` no
# formato "Artista · Álbum · Song · Ano" — é a única fonte pública do nome do
# álbum para uma faixa individual (o embed de faixa não inclui esse campo).
_OG_DESCRIPTION_RE = re.compile(
    r'<meta\s+(?=[^>]*\bproperty="og:description")[^>]*\bcontent="([^"]*)"',
    re.IGNORECASE,
)
_SOCIAL_CRAWLER_UA = "facebookexternalhit/1.1"

_ENTITY_PATHS = (
    ("props", "pageProps", "state", "data", "entity"),
    ("props", "pageProps", "data", "entity"),
    ("props", "pageProps", "entity"),
)

# A página de embed também carrega um token de acesso anônimo (usado pelo
# player incorporado pra tocar as prévias) em um desses caminhos. Não serve
# pra baixar áudio, mas dá acesso à API interna spclient — que devolve a
# playlist inteira, sem o limite de ~100 faixas da página de embed.
_TOKEN_PATHS = (
    ("props", "pageProps", "state", "settings", "session"),
    ("props", "pageProps", "settings", "session"),
    ("props", "pageProps", "session"),
)
_SPCLIENT_URL = "https://spclient.wg.spotify.com/playlist/v2/playlist/{id}"
# Faixas extras (além do embed) buscadas em paralelo — 4 é suficiente pra
# acelerar bastante sem parecer uma rajada de requisições pra Spotify.
_EXTRA_TRACKS_WORKERS = 4


class SpotifyClientError(Exception):
    """Erro genérico ao ler dados públicos da Spotify."""


class InvalidSpotifyURLError(SpotifyClientError):
    """URL/URI da Spotify ausente, malformada ou de tipo inesperado."""


def detect_url_type(url: str) -> tuple[str, str]:
    """Retorna (tipo, id) a partir de uma URL/URI da Spotify.

    `tipo` é "track", "album" ou "playlist". Aceita URLs canônicas,
    prefixadas por idioma (`/intl-xx/`) e URIs (`spotify:tipo:id`).
    """
    if not url:
        raise InvalidSpotifyURLError("URL/URI da Spotify vazia.")
    match = _SPOTIFY_ID_RE.search(url)
    if not match:
        raise InvalidSpotifyURLError(f"URL/URI da Spotify inválida: {url!r}")
    return match.group("type"), match.group("id")


def _resolve_path(data: dict, path: tuple[str, ...]):
    result = data
    for key in path:
        if not isinstance(result, dict):
            return None
        result = result.get(key)
    return result


def _deep_find(data: dict, key: str, max_depth: int = 6) -> dict | None:
    if not isinstance(data, dict) or max_depth <= 0:
        return None
    if key in data:
        return data
    for value in data.values():
        if isinstance(value, dict):
            found = _deep_find(value, key, max_depth - 1)
            if found is not None:
                return found
    return None


class SpotifyClient:
    """Cliente somente-leitura de faixas/álbuns/playlists públicos da Spotify.

    Não requer credenciais: raspa a mesma página de embed que o player
    incorporado da Spotify usa. Cobre playlists/álbuns de até ~100 faixas
    (o limite da página de embed) — para além disso, a Spotify exige a API
    autenticada, fora do escopo deste projeto.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._cached_token: str | None = None

    def get_track(self, track_url: str) -> dict:
        """Retorna os metadados de uma única faixa."""
        track_id = self._extract_id(track_url, "track")
        entity = self._fetch_entity("track", track_id)
        track = self._parse_single_track(entity, track_id)
        if not track["album"]:
            track["album"] = self._fetch_track_album(track_id) or ""
        return track

    def get_album_tracks(self, album_url: str) -> list[dict]:
        """Retorna as faixas de um álbum público."""
        album_id = self._extract_id(album_url, "album")
        entity = self._fetch_entity("album", album_id)
        album_name = entity.get("name") or "Unknown Album"
        cover_url = self._extract_cover(entity)
        return self._parse_track_list(entity, fallback_album=album_name, fallback_cover=cover_url)

    def get_playlist_tracks(self, playlist_url: str) -> list[dict]:
        """Retorna as faixas de uma playlist pública.

        A página de embed só traz até ~100 faixas; para playlists maiores,
        busca o restante via spclient (API interna que o player usa),
        buscando os metadados de cada faixa extra em paralelo.
        """
        playlist_id = self._extract_id(playlist_url, "playlist")
        entity = self._fetch_entity("playlist", playlist_id)
        cover_url = self._extract_cover(entity)
        tracks = self._parse_track_list(entity, fallback_album=None, fallback_cover=cover_url)

        if not self._cached_token:
            return tracks

        known_ids = {t["id"] for t in tracks}
        extra_ids = [
            tid for tid in self._fetch_spclient_track_ids(playlist_id) if tid not in known_ids
        ]
        if not extra_ids:
            return tracks

        def _fetch_one(track_id: str) -> dict | None:
            try:
                track = self._parse_single_track(
                    self._fetch_entity("track", track_id), track_id
                )
                if not track["album"]:
                    track["album"] = self._fetch_track_album(track_id) or ""
                track["cover_url"] = track["cover_url"] or cover_url
                return track
            except SpotifyClientError:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=_EXTRA_TRACKS_WORKERS) as pool:
            extra_tracks = [t for t in pool.map(_fetch_one, extra_ids) if t]

        tracks.extend(extra_tracks)
        return tracks

    def get_container_name(self, url: str) -> str:
        """Nome da playlist/álbum, usado para nomear a pasta de destino."""
        content_type, content_id = detect_url_type(url)
        if content_type == "track":
            raise InvalidSpotifyURLError("Esperava-se uma URL de álbum ou playlist.")
        entity = self._fetch_entity(content_type, content_id)
        return str(entity.get("name") or entity.get("title") or "Unknown")

    # -- internals ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
            "user-agent": _USER_AGENT,
        }

    def _extract_id(self, url: str, expected_type: str) -> str:
        url_type, content_id = detect_url_type(url)
        if url_type != expected_type:
            raise InvalidSpotifyURLError(
                f"Era esperado(a) um(a) {expected_type}, mas a URL é de {url_type}: {url!r}"
            )
        return content_id

    def _fetch_entity(self, content_type: str, content_id: str) -> dict:
        url = _EMBED_URLS[content_type].format(id=content_id)
        try:
            resp = self._session.get(url, headers=self._headers(), timeout=20)
        except requests.RequestException as e:
            raise SpotifyClientError(f"Falha de rede ao acessar a Spotify: {e}") from e

        if resp.status_code == 429:
            raise SpotifyClientError("Rate limit atingido pela Spotify. Tente novamente em instantes.")
        if resp.status_code in (401, 403):
            raise SpotifyClientError(
                f"Acesso negado (HTTP {resp.status_code}). O conteúdo pode ser privado ou indisponível."
            )
        if resp.status_code == 404:
            raise SpotifyClientError(f"{content_type.capitalize()} não encontrado(a): {content_id}")
        if resp.status_code != 200:
            raise SpotifyClientError(f"Spotify retornou HTTP {resp.status_code}.")

        match = _NEXT_DATA_RE.search(resp.text)
        if not match:
            raise SpotifyClientError(
                "Não foi possível localizar os dados da página (layout da Spotify pode ter mudado)."
            )
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise SpotifyClientError(f"JSON inválido na página da Spotify: {e}") from e

        self._cache_token(data)
        return self._extract_entity(data, content_type, content_id)

    def _cache_token(self, data: dict) -> None:
        for path in _TOKEN_PATHS:
            session_data = _resolve_path(data, path)
            if isinstance(session_data, dict) and session_data.get("accessToken"):
                self._cached_token = session_data["accessToken"]
                return

    def _fetch_spclient_track_ids(self, playlist_id: str) -> list[str]:
        """IDs de todas as faixas da playlist, direto do spclient (sem o
        limite de ~100 da página de embed). Retorna lista vazia em qualquer
        falha — é um fallback opcional, não deve derrubar o resto da busca."""
        if not self._cached_token:
            return []
        headers = {"Authorization": f"Bearer {self._cached_token}", "Accept": "application/json"}
        try:
            resp = self._session.get(
                _SPCLIENT_URL.format(id=playlist_id), headers=headers, timeout=30
            )
        except requests.RequestException:
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        items = ((data.get("contents") or {}).get("items")) or []
        ids = []
        for item in items:
            uri = item.get("uri", "")
            if uri.startswith("spotify:track:"):
                ids.append(uri.split(":")[-1])
        return ids

    def _extract_entity(self, data: dict, content_type: str, content_id: str) -> dict:
        for path in _ENTITY_PATHS:
            result = _resolve_path(data, path)
            if isinstance(result, dict):
                return result

        # Spotify faz testes A/B com estruturas de página diferentes; se os
        # caminhos conhecidos falharem, procura recursivamente por um dict
        # que pareça a entidade (tem trackList ou um campo "type" conhecido).
        container = _deep_find(data, "trackList")
        if isinstance(container, dict):
            return container
        container = _deep_find(data, "type")
        if isinstance(container, dict) and container.get("type") in ("playlist", "track", "album"):
            return container

        raise SpotifyClientError(
            f"Não foi possível extrair os dados de {content_type} {content_id} "
            "(estrutura da página da Spotify mudou)."
        )

    def _extract_cover(self, entity: dict) -> str | None:
        cover_art = entity.get("coverArt") or {}
        sources = cover_art.get("sources") or []
        if sources:
            return sources[-1].get("url")
        images = (entity.get("visualIdentity") or {}).get("image") or []
        for img in images:
            if isinstance(img, dict) and img.get("url"):
                return img.get("url")
        return None

    def _parse_track_list(
        self, entity: dict, fallback_album: str | None, fallback_cover: str | None
    ) -> list[dict]:
        tracks = []
        for item in entity.get("trackList", []):
            if not isinstance(item, dict):
                continue
            uri = item.get("uri", "")
            if not uri.startswith("spotify:track:"):
                continue
            track_id = uri.split(":")[-1]

            title = item.get("title") or item.get("name") or "Unknown Track"
            artists = item.get("subtitle") or item.get("artists") or ""
            if isinstance(artists, list):
                artists = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))

            album = None
            if isinstance(item.get("album"), dict):
                album = item["album"].get("name")

            duration_ms = item.get("duration") or 0

            tracks.append(
                {
                    "id": track_id,
                    "name": str(title),
                    "artist": str(artists),
                    "album": album or fallback_album or "",
                    "cover_url": fallback_cover,
                    "duration_ms": int(duration_ms),
                    "release_date": item.get("releaseDate"),
                }
            )
        return tracks

    def _parse_single_track(self, entity: dict, track_id: str) -> dict:
        title = entity.get("name") or entity.get("title") or "Unknown Track"

        artists_data = entity.get("artists", [])
        if isinstance(artists_data, list) and artists_data:
            artists = ", ".join(a.get("name", "") for a in artists_data if isinstance(a, dict))
        else:
            artists = entity.get("subtitle", "") or ""

        release_date = None
        rd = entity.get("releaseDate")
        if isinstance(rd, dict):
            release_date = (rd.get("isoString") or "")[:10]
        elif isinstance(rd, str):
            release_date = rd

        return {
            "id": track_id,
            "name": str(title),
            "artist": str(artists),
            "album": "",  # o embed de faixa individual não inclui álbum
            "cover_url": self._extract_cover(entity),
            "duration_ms": int(entity.get("duration") or 0),
            "release_date": release_date,
        }

    def _fetch_track_album(self, track_id: str) -> str | None:
        """Extrai o nome do álbum da tag `og:description` da página pública da faixa.

        A Spotify serve HTML diferente por User-Agent: navegadores comuns
        recebem uma casca React sem essa meta tag; um user-agent de
        crawler social (usado por Facebook/Discord/iMessage para gerar
        pré-visualizações de link) recebe a página SEO completa, que traz
        `og:description` no formato "Artista · Álbum · Song · Ano".
        """
        headers = self._headers()
        headers["user-agent"] = _SOCIAL_CRAWLER_UA
        try:
            resp = self._session.get(
                _TRACK_PAGE_URL.format(id=track_id), headers=headers, timeout=15
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        match = _OG_DESCRIPTION_RE.search(resp.text)
        if not match:
            return None
        parts = _html.unescape(match.group(1)).split(" · ")
        return parts[1].strip() if len(parts) >= 2 and parts[1].strip() else None


if __name__ == "__main__":
    # Teste manual: imprime os dados de uma playlist, um álbum e uma faixa públicos.
    example_playlist = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
    example_album = "https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv"
    example_track = "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3"

    client = SpotifyClient()
    try:
        print(f"Playlist: {example_playlist}")
        for t in client.get_playlist_tracks(example_playlist)[:5]:
            print(f"  - {t['artist']} - {t['name']} ({t['duration_ms']} ms)")

        print(f"\nÁlbum: {example_album}")
        for t in client.get_album_tracks(example_album)[:5]:
            print(f"  - {t['artist']} - {t['name']} ({t['duration_ms']} ms)")

        print(f"\nFaixa: {example_track}")
        track = client.get_track(example_track)
        print(f"  - {track['artist']} - {track['name']} | álbum: {track['album']}")
        print(f"  - capa: {track['cover_url']}")
    except SpotifyClientError as e:
        print(f"Erro: {e}")
