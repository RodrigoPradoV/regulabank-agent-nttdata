"""Menciones abiertas con GLiNER2 (`fastino/gliner2-large-v1`): roles, productos, sanciones, reportes y obligaciones.

Importa el modelo de forma perezosa: la suite y el build con `--no-gliner2` corren sin torch. Si el paquete no
esta instalado, `load_model` falla con el comando de instalacion. Umbral bajo al extraer (0,3, se guarda el
score); el corte (0,5) lo aplica `aggregate` (docs/04-entities.md, "Filtro y voto").
"""

from __future__ import annotations

import time
from typing import Any

import pyarrow as pa

from regulabank.graphs.entities import Mention, norm_key, to_table

INSTALL_HINT = 'GLiNER2 no esta instalado: uv pip install -e ".[models]" --python .venv/bin/python'

# Etiqueta -> descripcion en espanol (GLiNER2 acepta {nombre: descripcion}).
LABELS: dict[str, str] = {
    "role": "cargo, organo o unidad responsable dentro de la empresa, como Oficial de Cumplimiento, Directorio, "
            "Gerencia General o Auditoria Interna",
    "product": "producto o servicio financiero, como credito hipotecario, tarjeta de credito o deposito a plazo",
    "sanction": "sancion o medida correctiva, como multa, amonestacion, suspension o intervencion",
    "report": "reporte, anexo, registro o formato que se remite al regulador, como Anexo N.° 6 o Reporte de "
              "Operaciones Sospechosas",
    "obligation": "obligacion o prohibicion impuesta a la empresa, como debera remitir, esta prohibido o debe "
                  "contar con",
}


class Gliner2NotInstalled(RuntimeError):
    """El extra `models` no esta instalado."""


def load_model(model_name: str = "fastino/gliner2-large-v1", device: str | None = None) -> Any:
    """Carga el modelo (CPU por defecto; `device="mps"` en Apple Silicon)."""
    try:
        from gliner2 import GLiNER2  # noqa: PLC0415 - import perezoso a proposito
    except ImportError as exc:
        raise Gliner2NotInstalled(INSTALL_HINT) from exc
    model = GLiNER2.from_pretrained(model_name)
    if device:
        model = model.to(device)
    return model.eval()


def _entities_of(result: Any) -> dict[str, list[Any]]:
    if isinstance(result, dict) and isinstance(result.get("entities"), dict):
        return result["entities"]
    return result if isinstance(result, dict) else {}


def _locate(text: str, item: Any) -> tuple[str, int, int, float] | None:
    """Devuelve (mention, start, end, score) verificando el tramo literal; None si no se puede anclar."""
    if isinstance(item, dict):
        surface = str(item.get("text", ""))
        score = float(item.get("confidence", 1.0))
        start, end = item.get("start"), item.get("end")
        if start is not None and end is not None and text[start:end] == surface:
            return surface, int(start), int(end), score
    else:
        surface, score = str(item), 1.0
    if not surface:
        return None
    pos = text.find(surface)
    return (surface, pos, pos + len(surface), score) if pos >= 0 else None


def extract(chunks: pa.Table, model: Any, threshold: float = 0.3, batch_size: int = 8,
            labels: dict[str, str] | None = None, chunk_size: int = 384, chunk_overlap: int = 64) -> pa.Table:
    """Tabla CHUNKS -> tabla MENTIONS (method gliner2). Ventanas por palabras bajo el tope del modelo."""
    labels = labels or LABELS
    ids = chunks["chunk_id"].to_pylist()
    texts = chunks["text"].to_pylist()
    t0 = time.perf_counter()
    results = model.batch_extract_entities_long(
        texts, labels, batch_size=batch_size, threshold=threshold, include_confidence=True, include_spans=True,
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    elapsed = time.perf_counter() - t0
    mentions: list[Mention] = []
    for chunk_id, text, result in zip(ids, texts, results):
        seen: set[tuple[int, int, str]] = set()
        for label, items in _entities_of(result).items():
            if label not in labels:
                continue
            for item in items or []:
                located = _locate(text, item)
                if located is None:
                    continue
                surface, start, end, score = located
                if (start, end, label) in seen or score < threshold:
                    continue
                seen.add((start, end, label))
                mentions.append(Mention(chunk_id, f"{label}:{norm_key(surface)}", label, surface, start, end,
                                        score=score, method="gliner2", value=None))
    table = to_table(mentions)
    table = table.replace_schema_metadata({"gliner2_seconds": f"{elapsed:.3f}", "gliner2_chunks": str(len(ids))})
    return table


def merge(base: pa.Table, extra: pa.Table) -> pa.Table:
    """Une menciones regex/gazetteer con las de GLiNER2; ante solape en el mismo chunk gana la base."""
    taken: dict[str, list[tuple[int, int]]] = {}
    for r in base.select(["chunk_id", "start", "end"]).to_pylist():
        taken.setdefault(r["chunk_id"], []).append((r["start"], r["end"]))
    keep = []
    for r in extra.to_pylist():
        spans = taken.get(r["chunk_id"], [])
        if any(r["start"] < e and r["end"] > s for s, e in spans):
            continue
        keep.append(r)
    merged = pa.concat_tables([base, pa.Table.from_pylist(keep, schema=base.schema)]) if keep else base
    return merged.replace_schema_metadata(extra.schema.metadata)
