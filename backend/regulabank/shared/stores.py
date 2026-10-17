"""Conexiones a los dos almacenes: FalkorDB (grafo) y LanceDB (vectores + FTS)."""

from __future__ import annotations

import lancedb
from falkordb import FalkorDB, Graph

from regulabank.shared.config import Settings


def graph(settings: Settings) -> Graph:
    """Grafo unico `regulabank` con las cuatro capas logicas (docs/06-graphs.md)."""
    client = FalkorDB(host=settings.falkor_host, port=settings.falkor_port)
    return client.select_graph(settings.falkor_graph)


def lance(settings: Settings) -> lancedb.DBConnection:
    """Un directorio LanceDB por release; se crea si no existe."""
    settings.lance_dir.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(settings.lance_dir))
