"""Prueba de humo: escribe y lee un chunk en LanceDB y un par Norm -> Article en FalkorDB.

Corre igual dentro del contenedor `app` o en la laptop (`uv run python scripts/smoke.py`).
Sale con 1 si cualquiera de los dos almacenes no responde como se espera.
"""

from __future__ import annotations

import sys
import time

import pyarrow as pa
from lancedb.index import FTS

from regulabank.shared import config, stores


def check_lance(settings: config.Settings) -> str:
    db = stores.lance(settings)
    rows = [
        {"chunk_id": "c_smoke1", "norm_id": "pe-smoke-res-1-2026", "article_no": "1",
         "text": "Artículo 1.- La presente norma entra en vigencia al día siguiente de su publicación.",
         "vector": [0.1, 0.2, 0.3, 0.4]},
        {"chunk_id": "c_smoke2", "norm_id": "pe-smoke-res-1-2026", "article_no": "2",
         "text": "Artículo 2.- Las empresas remitirán el reporte dentro de los quince (15) días hábiles.",
         "vector": [0.9, 0.1, 0.0, 0.2]},
    ]
    schema = pa.schema([
        ("chunk_id", pa.string()), ("norm_id", pa.string()), ("article_no", pa.string()),
        ("text", pa.string()), ("vector", pa.list_(pa.float32(), 4)),
    ])
    table = db.create_table("smoke", data=rows, schema=schema, mode="overwrite")
    table.create_index("text", config=FTS(language="Spanish"), replace=True)
    dense = table.search([0.9, 0.1, 0.0, 0.2]).limit(1).to_list()
    fts = table.search("quince", query_type="fts").limit(1).to_list()
    assert dense[0]["chunk_id"] == "c_smoke2", dense
    assert fts[0]["chunk_id"] == "c_smoke2", fts
    db.drop_table("smoke")
    return f"lance ok ({settings.lance_dir}): denso y fts devuelven c_smoke2"


def check_falkor(settings: config.Settings) -> str:
    g = stores.graph(settings)
    g.query("MERGE (n:Norm {id: $nid}) SET n.short = $short", {"nid": "pe-smoke-res-1-2026", "short": "Res. smoke 1-2026"})
    g.query(
        "MATCH (n:Norm {id: $nid}) MERGE (a:Article {id: $aid}) SET a.no = '1' MERGE (n)-[:HAS_ARTICLE]->(a)",
        {"nid": "pe-smoke-res-1-2026", "aid": "pe-smoke-res-1-2026#art-1"},
    )
    res = g.query("MATCH (n:Norm {id: $nid})-[:HAS_ARTICLE]->(a) RETURN count(a)", {"nid": "pe-smoke-res-1-2026"})
    count = res.result_set[0][0]
    assert count == 1, res.result_set
    g.query("MATCH (n:Norm {id: $nid}) OPTIONAL MATCH (n)-[]->(a:Article) DETACH DELETE n, a", {"nid": "pe-smoke-res-1-2026"})
    return f"falkor ok ({settings.falkor_host}:{settings.falkor_port}/{settings.falkor_graph}): Norm -> Article"


def main() -> int:
    settings = config.load()
    failures = 0
    for check in (check_lance, check_falkor):
        t0 = time.perf_counter()
        try:
            msg = check(settings)
            print(f"OK   {msg} [{(time.perf_counter() - t0) * 1000:.0f} ms]")
        except Exception as exc:  # noqa: BLE001 - la prueba de humo reporta cualquier falla y sigue
            failures += 1
            print(f"FAIL {check.__name__}: {type(exc).__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
