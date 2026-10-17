"""Lectura de `seeds/params.toml`: los parametros efectivos de la etapa, con su fuente en el propio archivo."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

PARAMS_PATH = Path(__file__).resolve().parents[2] / "seeds" / "params.toml"


def load(path: Path = PARAMS_PATH) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)
