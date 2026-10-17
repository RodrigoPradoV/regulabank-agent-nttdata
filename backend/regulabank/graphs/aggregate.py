"""MENTIONS -> ENTITIES: una fila por entidad canonica con n_chunks, n_norms y catalog_id.

Curaduria por entidad (docs/04-entities.md): entra si aparece en >= `min_chunks` chunks o si su tipo vale con una
sola ocurrencia (`always_keep_types`). Las menciones de GLiNER2 solo cuentan con score >= `gliner2_cut`.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from regulabank.graphs import params as params_mod
from regulabank.shared import schema


def keep_mask(mentions: pa.Table, params: dict[str, Any] | None = None) -> pa.Array:
    """Mascara de las menciones que cuentan: todas las de regex/gazetteer, GLiNER2 solo sobre el corte."""
    params = params or params_mod.load()
    cut = float(params["entities"]["gliner2_cut"])
    is_model = pc.equal(mentions["method"], "gliner2")
    return pc.or_(pc.invert(is_model), pc.greater_equal(mentions["score"], cut))


def _name_for(type_: str, value: dict[str, Any] | None, surfaces: Counter[str], entity_id: str) -> str:
    v = value or {}
    if type_ in ("regulator", "institution_type", "risk", "product", "report", "role") and v.get("name"):
        return str(v["name"])
    if type_ == "defined_term" and v.get("term"):
        return str(v["term"])
    if type_ == "norm_ref":
        return str(v.get("norm_id") or v.get("raw") or surfaces.most_common(1)[0][0])
    if type_ == "article_ref":
        return entity_id.split(":", 1)[1]
    if type_ == "deadline" and "n" in v:
        return f"{v['n']} {v['unit']}"
    if type_ == "amount" and "value" in v:
        return f"{v['currency']} {v['value']}"
    if type_ == "percentage" and "value" in v:
        return f"{v['value']} %"
    return surfaces.most_common(1)[0][0]


def aggregate(mentions: pa.Table, chunks: pa.Table, params: dict[str, Any] | None = None) -> pa.Table:
    """Tabla MENTIONS + tabla CHUNKS (para norm_id por chunk) -> tabla ENTITIES."""
    params = params or params_mod.load()
    min_chunks = int(params["entities"]["min_chunks"])
    always = set(params["entities"]["always_keep_types"])
    norm_of = dict(zip(chunks["chunk_id"].to_pylist(), chunks["norm_id"].to_pylist()))

    kept = mentions.filter(keep_mask(mentions, params))
    chunk_sets: dict[str, set[str]] = defaultdict(set)
    surfaces: dict[str, Counter[str]] = defaultdict(Counter)
    types: dict[str, str] = {}
    values: dict[str, dict[str, Any]] = {}
    catalog: dict[str, str] = {}
    for r in kept.to_pylist():
        eid = r["entity_id"]
        chunk_sets[eid].add(r["chunk_id"])
        surfaces[eid][r["mention"]] += 1
        types.setdefault(eid, r["type"])
        value = json.loads(r["value"]) if r["value"] else None
        if value:
            # Para terminos definidos vale la fila de la definicion (defined_in no nulo) sobre la del uso.
            if eid not in values or (value.get("defined_in") and not values[eid].get("defined_in")):
                values[eid] = value
            if value.get("catalog_id"):
                catalog[eid] = value["catalog_id"]

    rows = []
    for eid, chunk_ids in chunk_sets.items():
        type_ = types[eid]
        if len(chunk_ids) < min_chunks and type_ not in always:
            continue
        rows.append({
            "entity_id": eid, "type": type_,
            "name": _name_for(type_, values.get(eid), surfaces[eid], eid),
            "key": eid.split(":", 1)[1],
            "catalog_id": catalog.get(eid),
            "n_chunks": len(chunk_ids),
            "n_norms": len({norm_of.get(c) for c in chunk_ids}),
        })
    rows.sort(key=lambda r: (r["type"], r["entity_id"]))
    return pa.Table.from_pylist(rows, schema=schema.ENTITIES)
