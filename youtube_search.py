"""Busca no YouTube pela melhor correspondência de áudio para uma faixa da Spotify.

Como a Spotify só entrega metadados (não o áudio), cada faixa precisa de uma
busca equivalente no YouTube. A estratégia: pega vários resultados (não só o
primeiro, que pode estar bloqueado por região ou ser a faixa errada), filtra
por título plausível, depois por artista, e entre os candidatos restantes
escolhe o de duração mais próxima — rejeitando o resultado se mesmo o mais
próximo estiver muito longe da duração esperada (evita baixar remix/live/cover
no lugar da faixa original).
"""

from __future__ import annotations

import re
import unicodedata

from yt_dlp import YoutubeDL

# Diferença máxima (segundos) entre a duração da faixa e do vídeo do YouTube
# para considerá-los a mesma gravação.
DURATION_TOLERANCE_WIDE_S = 30

# Indícios de que o upload é uma versão ao vivo/acústica, não o estúdio que a
# Spotify manda buscar. Checado no título ORIGINAL (antes de _normalize, que
# apaga o conteúdo entre parênteses — é lá que esse indício costuma estar).
_LIVE_VARIANT_RE = re.compile(
    r"\b(ao\s*vivo|live|acoustic|ac[uú]stic\w*|unplugged)\b", re.IGNORECASE
)


def _is_live_variant(title: str | None) -> bool:
    return bool(title and _LIVE_VARIANT_RE.search(title))

_SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": True,
    "ignoreerrors": True,
    "retries": 5,
    "socket_timeout": 15,
}


def _normalize(text: str | None) -> str:
    """Minúsculas, sem acentos, sem parênteses/colchetes/`feat.`, só letras/números."""
    if not text:
        return ""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\b(feat\.?|ft\.?)\s+.*$", "", text, flags=re.IGNORECASE)
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _spotify_title_core(title: str | None) -> str:
    """Remove o sufixo ' - Variante' que a Spotify usa (ex: '- Remastered 2011')."""
    if not title:
        return ""
    return title.split(" - ", 1)[0]


def _title_matches(yt_title: str | None, expected_title: str | None) -> bool:
    yt = _normalize(yt_title)
    target = _normalize(_spotify_title_core(expected_title))
    if not target or not yt:
        return False
    if len(target) >= 4:
        return target in yt
    return target in yt.split()


class YouTubeSearcher:
    """Pesquisa no YouTube e escolhe o melhor vídeo para uma faixa da Spotify."""

    def search(self, track: dict) -> str | None:
        """Retorna a URL do melhor vídeo do YouTube para `track`, ou None."""
        query = f"ytsearch5:{track['name']} {track['artist']} audio"
        expected_duration_s = (track.get("duration_ms") or 0) / 1000 or None

        entries = self._raw_search(query)
        if not entries:
            return None

        title_matches = [e for e in entries if _title_matches(e.get("title"), track["name"])]
        if not title_matches:
            return None

        pool = self._filter_by_artist(title_matches, track.get("artist", ""))
        if not pool:
            return None

        # Prefere a versão de estúdio quando ela também está no pool; só usa
        # ao vivo/acústico se for a única opção disponível.
        studio_pool = [e for e in pool if not _is_live_variant(e.get("title"))]
        if studio_pool:
            pool = studio_pool

        chosen = pool[0]
        if expected_duration_s:
            timed = [e for e in pool if e.get("duration")]
            if timed:
                chosen = min(timed, key=lambda e: abs(e["duration"] - expected_duration_s))
                if abs(chosen["duration"] - expected_duration_s) > DURATION_TOLERANCE_WIDE_S:
                    return None  # candidato mais próximo ainda está longe demais

        return f"https://www.youtube.com/watch?v={chosen['id']}"

    def _raw_search(self, query: str) -> list[dict]:
        try:
            with YoutubeDL(_SEARCH_OPTS) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception:
            return []
        return [e for e in (info or {}).get("entries", []) if e and e.get("id")]

    def _filter_by_artist(self, candidates: list[dict], artists: str) -> list[dict]:
        """Prefere candidatos com o artista no título, mas não rejeita tudo se
        nenhum bater (nem sempre o upload do YouTube inclui o artista)."""
        raw_tokens = re.split(r"[,&]+|\s+(?:feat\.?|ft\.?)\s+", artists, flags=re.IGNORECASE)
        artist_tokens = [_normalize(t) for t in raw_tokens if _normalize(t)]
        if not artist_tokens:
            return candidates

        matched = [
            e
            for e in candidates
            if any(token in _normalize(e.get("title") or "") for token in artist_tokens)
        ]
        return matched or candidates
