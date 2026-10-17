"""Carga y validacion de seeds/norms.csv: una fila por norma.

Columnas obligatorias = schema.NORMS menos source_sha256. Columnas opcionales: `jurisdiction` (PE por defecto) y
`aliases` (nombres cortos separados por `|`, como «Ley General» o «Reglamento de Provisiones») que la etapa graphs
usa para resolver referencias a la norma. `source_path` relativa se resuelve contra el directorio del CSV.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pyarrow as pa

from regulabank.shared import schema

CSV_COLUMNS = tuple(f.name for f in schema.NORMS if f.name != "source_sha256")
OPTIONAL_COLUMNS = ("jurisdiction", "aliases")
DEFAULT_JURISDICTION = "PE"
REQUIRED = ("norm_id", "short", "title", "kind", "issuer", "published", "valid_from", "status")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRUE = {"true", "1", "yes", "si", "sí"}
FALSE = {"false", "0", "no", ""}


@dataclass
class Norm:
    """Una norma tal como viene del CSV; capture completa source_path y source_sha256."""

    norm_id: str
    short: str
    title: str
    kind: str
    issuer: str
    published: str
    valid_from: str
    valid_to: str | None
    status: str
    topics: list[str] = field(default_factory=list)
    source_url: str | None = None
    source_path: str | None = None
    synthetic: bool = False
    source_sha256: str | None = None
    jurisdiction: str = DEFAULT_JURISDICTION
    aliases: list[str] = field(default_factory=list)

    def row(self) -> dict:
        """Fila lista para pa.Table.from_pylist con schema.NORMS (sin las columnas opcionales del CSV)."""
        names = {f.name for f in schema.NORMS}
        return {k: v for k, v in asdict(self).items() if k in names}


def _bool(value: str, norm_id: str) -> bool:
    v = (value or "").strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise ValueError(f"{norm_id}: synthetic debe ser true/false, no {value!r}")


def load_norms(path: Path) -> list[Norm]:
    """Lee el CSV y valida kinds, status, fechas ISO, ids unicos y que haya una fuente (url o ruta)."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: faltan columnas {missing}; se esperan {list(CSV_COLUMNS)}")
        rows = list(reader)

    norms: list[Norm] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, start=2):
        r = {k: (v or "").strip() for k, v in r.items() if k is not None}
        norm_id = r.get("norm_id", "")
        where = f"{path}:{i} ({norm_id or 'sin id'})"
        for col in REQUIRED:
            if not r.get(col):
                raise ValueError(f"{where}: columna obligatoria vacia: {col}")
        if norm_id in seen:
            raise ValueError(f"{where}: norm_id duplicado")
        seen.add(norm_id)
        if r["kind"] not in schema.NORM_KINDS:
            raise ValueError(f"{where}: kind {r['kind']!r} no esta en {schema.NORM_KINDS}")
        if r["status"] not in schema.NORM_STATUS:
            raise ValueError(f"{where}: status {r['status']!r} no esta en {schema.NORM_STATUS}")
        for col in ("published", "valid_from", "valid_to"):
            if r.get(col) and not ISO_DATE.match(r[col]):
                raise ValueError(f"{where}: {col} debe ser fecha ISO (AAAA-MM-DD), no {r[col]!r}")
        if not r.get("source_url") and not r.get("source_path"):
            raise ValueError(f"{where}: hace falta source_url o source_path")
        topics = [t.strip() for t in r.get("topics", "").split(";") if t.strip()]
        aliases = [a.strip() for a in r.get("aliases", "").split("|") if a.strip()]
        source_path = r.get("source_path") or None
        if source_path and not Path(source_path).is_absolute() and not Path(source_path).exists():
            source_path = str(path.parent / source_path)
        norms.append(
            Norm(
                norm_id=norm_id,
                short=r["short"],
                title=r["title"],
                kind=r["kind"],
                issuer=r["issuer"],
                published=r["published"],
                valid_from=r["valid_from"],
                valid_to=r.get("valid_to") or None,
                status=r["status"],
                topics=topics,
                source_url=r.get("source_url") or None,
                source_path=source_path,
                synthetic=_bool(r.get("synthetic", ""), norm_id),
                jurisdiction=r.get("jurisdiction") or DEFAULT_JURISDICTION,
                aliases=aliases,
            )
        )
    if not norms:
        raise ValueError(f"{path}: sin filas")
    return norms


def to_table(norms: list[Norm]) -> pa.Table:
    """Tabla con el esquema exacto de schema.NORMS."""
    return pa.Table.from_pylist([n.row() for n in norms], schema=schema.NORMS)
