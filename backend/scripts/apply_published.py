"""Vuelca `seeds/published.csv` a la columna `published` de corpus_chunks.parquet, por norm_id.

  python backend/scripts/apply_published.py --chunks data/corpus_v0/corpus_chunks.parquet [--out OTRO.parquet]

Solo escribe `published` donde el CSV trae fecha; no toca ninguna otra columna ni el texto. `precision` distingue
day (YYYY-MM-DD), month (YYYY-MM) y edition (fecha de la edicion del PDF cuando el emisor no da una sola).
Falla si una norma del parquet no esta en el CSV.
"""

import argparse
import csv
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "published.csv"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--chunks", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--seeds", type=Path, default=SEEDS)
    args = p.parse_args()
    dates = {r["norm_id"]: r["published"] or None for r in csv.DictReader(open(args.seeds, encoding="utf-8"))}
    table = pq.read_table(args.chunks)
    norms = set(table["norm_id"].to_pylist())
    missing = sorted(norms - set(dates))
    if missing:
        raise SystemExit(f"ABORT: normas sin fila en {args.seeds}: {missing}")
    column = pa.array([dates[n] for n in table["norm_id"].to_pylist()], pa.string())
    out = table.set_column(table.schema.get_field_index("published"), "published", column)
    pq.write_table(out, args.out or args.chunks)
    filled = sum(v is not None for v in column.to_pylist())
    print(f"published: {filled}/{out.num_rows} filas con fecha; normas sin fecha: "
          f"{sorted(n for n in norms if dates[n] is None)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
