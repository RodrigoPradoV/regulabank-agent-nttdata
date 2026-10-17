"""`ledger`: una linea JSONL por consulta, append-only -- se agrega, nunca se reescribe (docs/README.md)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[3] / "data" / "ledger" / "answer_graph.jsonl"


def append(entry: dict[str, Any], path: Path = DEFAULT_LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"logged_at": datetime.now(UTC).isoformat(), **entry}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_all(path: Path = DEFAULT_LEDGER_PATH) -> list[dict[str, Any]]:
    """Todas las lineas del ledger, en el orden en que se escribieron. Vacio si todavia no corrio nada."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
