"""Entorno leido en un solo lugar, con default. Los secretos nunca viven en codigo (docs/12-infra.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    model_provider: str
    falkor_host: str
    falkor_port: int
    falkor_graph: str
    lance_dir: Path
    release_id: str
    budget_usd_per_run: float
    http_user_agent: str
    embed_model: str


def load() -> Settings:
    """Lee las variables de entorno con sus defaults de desarrollo local."""
    return Settings(
        model_provider=os.getenv("MODEL_PROVIDER", "mock"),
        falkor_host=os.getenv("FALKOR_HOST", "127.0.0.1"),
        falkor_port=int(os.getenv("FALKOR_PORT", "6381")),
        falkor_graph=os.getenv("FALKOR_GRAPH", "regulabank"),
        lance_dir=Path(os.getenv("LANCE_DIR", "data/views/current/lancedb")),
        release_id=os.getenv("RELEASE_ID", "current"),
        budget_usd_per_run=float(os.getenv("BUDGET_USD_PER_RUN", "2.0")),
        http_user_agent=os.getenv("HTTP_USER_AGENT", "regulabank-hack/0.1"),
        embed_model=os.getenv("EMBED_MODEL", "google/embeddinggemma-300m"),
    )
