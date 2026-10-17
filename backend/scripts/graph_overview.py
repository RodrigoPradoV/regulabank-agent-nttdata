"""Resumen norma a norma del grafo, para la pagina /graph del frontend (JSON chico, sin los 47 mil aristas).

  python backend/scripts/graph_overview.py --graph data/graph_v0 --out graph-overview.json

Nodos: una norma (chunks, entidades, publicacion, aristas por tipo). Enlaces entre normas por capa:
  refers  REFERS_TO  dirigida (cita -> citada), cuenta chunks que citan
  similar SIMILAR    simetrica, cuenta aristas kNN y coseno medio
  nli     tabla NLI (no son aristas): pares de oraciones juzgados, contradicciones y implicaciones con p >= p_min
Cada numero sale de contar filas de los Parquet; nada se estima.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

NOT_TOPICAL = {"norm_ref", "article_ref"}


def build(graph: Path, p_min: float) -> dict:
    chunks = pq.read_table(graph / "chunks.parquet").to_pylist()
    entities = {r["entity_id"]: r for r in pq.read_table(graph / "entities.parquet").to_pylist()}
    mentions = pq.read_table(graph / "mentions.parquet").to_pylist()
    edges = pq.read_table(graph / "edges.parquet").to_pylist()
    nli = pq.read_table(graph / "nli" / "conflicts.parquet").to_pylist()
    norm_of = {c["chunk_id"]: c["norm_id"] for c in chunks}
    art_norm = {c["article_id"]: c["norm_id"] for c in chunks}
    n_chunks = len(chunks)

    nodes: dict[str, dict] = {}
    for c in chunks:
        n = nodes.setdefault(c["norm_id"], {"id": c["norm_id"], "short": c["norm_short"], "title": c["title"],
                                            "kind": c["norm_kind"], "status": c["status"],
                                            "published": c["published"], "chunks": 0,
                                            "edges": Counter(), "top_entities": []})
        n["chunks"] += 1

    def target_norm(e: dict) -> str | None:
        if e["dst_kind"] == "chunk":
            return norm_of.get(e["dst"])
        if e["dst_kind"] == "article":
            return art_norm.get(e["dst"])
        return e["dst"] if e["dst_kind"] == "norm" else None

    refers: Counter = Counter()
    similar: dict[tuple, list] = defaultdict(list)
    self_refs: Counter = Counter()
    for e in edges:
        src = norm_of.get(e["src"])
        if src is None:
            continue
        nodes[src]["edges"][e["type"]] += 1
        if e["type"] == "REFERS_TO":
            dst = target_norm(e)
            if dst is None:
                continue
            if dst == src:
                self_refs[src] += 1
            else:
                refers[(src, dst)] += 1
        elif e["type"] == "SIMILAR":
            dst = norm_of.get(e["dst"])
            if dst and dst != src:
                similar[tuple(sorted((src, dst)))].append(e["weight"])

    nli_pairs: dict[tuple, Counter] = defaultdict(Counter)
    for r in nli:
        a, b = norm_of[r["chunk_a"]], norm_of[r["chunk_b"]]
        k = tuple(sorted((a, b)))
        nli_pairs[k]["judged"] += 1
        if r["label"] == "contradiction" and r["p_contradiction"] >= p_min:
            nli_pairs[k]["contradiction"] += 1
        if r["label"] == "entailment" and r["p_entailment"] >= p_min:
            nli_pairs[k]["entailment"] += 1

    df = Counter(); per_norm: dict[str, Counter] = defaultdict(Counter)
    for m in mentions:
        ent = entities.get(m["entity_id"])
        if ent is None or ent["type"] in NOT_TOPICAL:
            continue
        per_norm[norm_of[m["chunk_id"]]][m["entity_id"]] += 1
    import math
    for nid, c in per_norm.items():
        scored = sorted(c.items(), key=lambda kv: -kv[1] * max(math.log(n_chunks / (1 + entities[kv[0]]["n_chunks"])), 0))
        nodes[nid]["top_entities"] = [{"name": entities[e]["name"], "type": entities[e]["type"], "mentions": k}
                                      for e, k in scored[:8]]
    for n in nodes.values():
        n["edges"] = dict(n["edges"])
    links = (
        [{"layer": "refers", "source": a, "target": b, "n": n} for (a, b), n in refers.items()]
        + [{"layer": "similar", "source": a, "target": b, "n": len(w), "cosine": round(sum(w) / len(w), 3)}
           for (a, b), w in similar.items()]
        + [{"layer": "nli", "source": a, "target": b, "n": c["contradiction"], "entailment": c["entailment"],
            "judged": c["judged"]} for (a, b), c in nli_pairs.items() if c["contradiction"]]
    )
    return {"p_min": p_min, "nodes": sorted(nodes.values(), key=lambda n: -n["chunks"]), "links": links,
            "self_refers": dict(self_refs),
            "totals": {"chunks": n_chunks, "entities": len(entities), "edges": len(edges),
                       "nli_pairs": len(nli)}}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--p-min", type=float, default=0.9, help="probabilidad minima para contar una relacion NLI")
    a = p.parse_args()
    data = build(a.graph, a.p_min)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['nodes'])} normas, {len(data['links'])} enlaces -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
