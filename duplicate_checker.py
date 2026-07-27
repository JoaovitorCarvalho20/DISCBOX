"""Detecção de faixas já baixadas, para evitar downloads duplicados.

A checagem é simplesmente "o arquivo de destino já existe
no disco?"  não é preciso um banco de dados separado, já que o nome do
arquivo é determinístico a partir do título/artista da faixa.
"""

from __future__ import annotations

from pathlib import Path


class DuplicateChecker:
    """Verifica se uma faixa já foi baixada com base na existência do arquivo."""

    def is_duplicate(self, filepath: Path) -> bool:
        return filepath.exists()
