"""Carga de `seeds/params.toml`: pesos de busqueda y umbrales de confianza, como dato, no como codigo.

Una persona los puede leer y ajustar sin tocar Python (docs/08-retrieval.md: "Parametros con procedencia en
seeds/params.toml"). Se cachea porque no cambian durante una corrida.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

SEEDS_PARAMS_PATH = Path(__file__).resolve().parents[2] / "seeds" / "params.toml"


@lru_cache(maxsize=4)
def load_params(path: Path = SEEDS_PARAMS_PATH) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)
