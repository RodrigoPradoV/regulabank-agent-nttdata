"""Vuelve a embeber los chunks con otro modelo (p. ej. openai:text-embedding-3-small) y escribe vectors.parquet.

  python scripts/reembed.py --chunks CHUNKS.parquet --model openai:text-embedding-3-small --out vectors.parquet          # solo estima
  python scripts/reembed.py ... --yes                                                                                   # llama a la API

Sin `--yes` no se llama a nada de pago: imprime caracteres, tokens estimados (caracteres / 3,5 para espanol) y USD estimado.
"""

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.graphs import embed as embed_mod
from regulabank.retrieval.search import clean_text
from regulabank.shared import schema

USD_PER_MTOK = {"openai:text-embedding-3-small": 0.02, "openai:text-embedding-3-large": 0.13}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--chunks", type=Path, required=True)
    p.add_argument("--model", default="openai:text-embedding-3-small")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--yes", action="store_true", help="confirma el gasto y llama a la API")
    a = p.parse_args()
    chunks = pq.read_table(a.chunks).select(schema.CHUNKS.names).cast(schema.CHUNKS)
    rows = chunks.select(["norm_short", "article_no", "text"]).to_pylist()
    chars = sum(len(clean_text(r["text"])) for r in rows)
    tokens = chars / 3.5
    usd = tokens / 1e6 * USD_PER_MTOK.get(a.model, 0.02)
    print(f"{len(rows)} chunks, {chars:,} caracteres, ~{tokens:,.0f} tokens, ~{usd:.3f} USD con {a.model}")
    if not a.yes:
        print("sin --yes: no se llamo a la API")
        return 0
    emb = embed_mod.OpenAIEmbedder(a.model)
    texts = [emb.doc_prefix(r["norm_short"] or "", r["article_no"] or "") + clean_text(r["text"]) for r in rows]
    vectors = emb.encode(texts)
    pq.write_table(embed_mod.vectors_table(chunks["chunk_id"].to_pylist(), vectors, emb.name), a.out)
    print(f"escrito {a.out}: {vectors.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
