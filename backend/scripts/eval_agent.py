"""Evalua el retrieval contra el golden (docs/10-evaluation.md) y compara estrategias con el baseline denso.

  python scripts/eval_agent.py --release RELEASE_DIR [--out eval.json] [--write-route seeds/route.csv]

Metricas (solo positivas): recall@5, recall@10, MRR, nDCG@8, por escenario y global, separando el golden de
desarrollo del RESERVADO (`reserved=true`: no se usa para elegir nada, solo se reporta). Abstencion: AUC de
`mean6` entre positivas y negativas, umbral = percentil 5 de las positivas de desarrollo, precision/recall sobre
negativas. Latencia p50/p95 por estrategia. Diferencia contra `dense` con bootstrap pareado (IC 95 %).

Relevante = el chunk es de la norma esperada y su `article_no` es el esperado o lo contiene/esta contenido
(6 vs 6.1). `--write-route` deja `dense_valid` (denso + vigencia) y solo cambia un escenario a `hybrid` o `hybrid_hop` si gana
en desarrollo por mas de `--min-gain` con al menos 3 preguntas Y no empeora en el reservado.
"""

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

from regulabank.agents.answer import detect_scenario
from regulabank.graphs import embed as embed_mod
from regulabank.retrieval.search import Retriever

STRATEGIES = ("dense", "dense_valid", "hybrid", "hybrid_hop")


def article_match(have: str | None, want: str) -> bool:
    have = (have or "").strip()
    return have == want or have.startswith(want + ".") or want.startswith(have + ".")


def metrics(rank: int | None) -> dict[str, float]:
    return {"r5": float(rank is not None and rank <= 5), "r10": float(rank is not None and rank <= 10),
            "mrr": 1.0 / rank if rank else 0.0, "ndcg8": 1.0 / math.log2(rank + 1) if rank and rank <= 8 else 0.0}


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def boot_diff(a: list[float], b: list[float], n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    rng = random.Random(seed)
    d = [x - y for x, y in zip(a, b)]
    means = sorted(statistics.fmean(rng.choices(d, k=len(d))) for _ in range(n))
    return statistics.fmean(d), means[int(0.025 * n)], means[int(0.975 * n)]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--questions", type=Path, default=Path(__file__).resolve().parents[1] / "seeds" / "questions.csv")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--write-route", type=Path, default=None)
    p.add_argument("--min-gain", type=float, default=0.05)
    p.add_argument("--device", default="mps")
    a = p.parse_args()

    qs = list(csv.DictReader(open(a.questions, encoding="utf-8")))
    emb = embed_mod.load_embedder("google/embeddinggemma-300m", "intfloat/multilingual-e5-small", 32, device=a.device)
    r = Retriever(a.release, emb, norms_csv=Path(__file__).resolve().parents[1] / "seeds" / "norms.csv")
    r.p["top_k"] = 10
    rows = r.rows

    per: dict[str, dict[str, dict]] = {s: {} for s in STRATEGIES}
    lat: dict[str, list[float]] = {s: [] for s in STRATEGIES}
    mean6: dict[str, float] = {}
    for q in qs:
        for s in STRATEGIES:
            res = r.search(q["text"], q["as_of"], strategy=s, quotes=False)
            lat[s].append(sum(res.trace.timings_ms.values()))
            mean6[q["question_id"]] = res.trace.evidence_mean6
            rank = None
            for i, h in enumerate(res.hits, 1):
                if q["expected_norm_id"] and h.norm_id == q["expected_norm_id"] and article_match(h.article_no, q["expected_article_no"]):
                    rank = i
                    break
            per[s][q["question_id"]] = metrics(rank) | {"rank": rank}

    pos = [q for q in qs if q["expected_abstain"] != "true"]
    neg = [q for q in qs if q["expected_abstain"] == "true"]
    dev = [q for q in pos if q["reserved"] != "true"]
    res_ = [q for q in pos if q["reserved"] == "true"]
    out: dict = {"n": {"questions": len(qs), "positive": len(pos), "negative": len(neg), "dev": len(dev), "reserved": len(res_)}}

    def agg(s: str, subset: list[dict], key: str) -> float:
        return statistics.fmean(per[s][q["question_id"]][key] for q in subset) if subset else float("nan")

    out["global"] = {s: {"dev": {k: round(agg(s, dev, k), 3) for k in ("r5", "r10", "mrr", "ndcg8")},
                         "reserved": {k: round(agg(s, res_, k), 3) for k in ("r5", "r10", "mrr", "ndcg8")},
                         "latency_ms": {"p50": round(float(np.percentile(lat[s], 50))), "p95": round(float(np.percentile(lat[s], 95)))}}
                     for s in STRATEGIES}
    out["vs_dense_ndcg8"] = {}
    for s in STRATEGIES[1:]:
        for name, sub in (("dev", dev), ("reserved", res_)):
            d, lo, hi = boot_diff([per[s][q["question_id"]]["ndcg8"] for q in sub], [per["dense"][q["question_id"]]["ndcg8"] for q in sub])
            out["vs_dense_ndcg8"][f"{s}_{name}"] = {"diff": round(d, 3), "ci95": [round(lo, 3), round(hi, 3)]}
    scen: dict[str, dict] = defaultdict(dict)
    for sc in sorted({q["scenario"] for q in pos}):
        sub = [q for q in pos if q["scenario"] == sc]
        sdev = [q for q in sub if q["reserved"] != "true"]
        sres = [q for q in sub if q["reserved"] == "true"]
        scen[sc] = {"n": len(sub), "n_dev": len(sdev), "n_reserved": len(sres),
                    **{s: {"ndcg8_dev": round(agg(s, sdev, "ndcg8"), 3), "ndcg8_reserved": round(agg(s, sres, "ndcg8"), 3),
                           "r5_all": round(agg(s, sub, "r5"), 3)} for s in STRATEGIES}}
    out["by_scenario"] = scen

    mp = [mean6[q["question_id"]] for q in pos]
    mn = [mean6[q["question_id"]] for q in neg]
    floor = float(np.percentile([mean6[q["question_id"]] for q in dev], 5))
    abstained_neg = sum(m < floor for m in mn)
    abstained_pos = [q["question_id"] for q in pos if mean6[q["question_id"]] < floor]
    out["abstention"] = {"auc_mean6": auc(mp, mn), "floor_p5_dev": round(floor, 4),
                         "negatives_abstained": f"{abstained_neg}/{len(neg)}", "positives_wrongly_abstained": len(abstained_pos),
                         "precision": round(abstained_neg / (abstained_neg + len(abstained_pos)), 3) if (abstained_neg + len(abstained_pos)) else None,
                         "recall": round(abstained_neg / len(neg), 3) if neg else None,
                         "mean6_positive": round(statistics.fmean(mp), 3), "mean6_negative": round(statistics.fmean(mn), 3)}
    out["scenario_detection"] = {"accuracy": round(statistics.fmean(detect_scenario(q["text"]) == q["scenario"] for q in pos), 3),
                                 "wrong": [(q["question_id"], q["scenario"], detect_scenario(q["text"])) for q in pos if detect_scenario(q["text"]) != q["scenario"]]}

    route = {}
    for sc, d in scen.items():
        best = "dense_valid"          # baseline con vigencia: lo que entra por defecto
        base = d["dense_valid"]["ndcg8_dev"]
        for s in ("hybrid", "hybrid_hop"):
            if d["n_dev"] >= 3 and d[s]["ndcg8_dev"] - base > a.min_gain and d[s]["ndcg8_reserved"] >= d["dense_valid"]["ndcg8_reserved"]:
                best, base = s, d[s]["ndcg8_dev"]
        route[sc] = best
    out["route"] = route
    out["misses"] = {s: [(q["question_id"], q["scenario"], per[s][q["question_id"]]["rank"]) for q in pos if per[s][q["question_id"]]["rank"] is None] for s in STRATEGIES}
    text = json.dumps(out, ensure_ascii=False, indent=2, default=str)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    print(text)
    if a.write_route:
        with open(a.write_route, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["scenario", "strategy"])
            w.writerows(sorted(route.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
