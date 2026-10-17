"""Corre el agente real sobre las preguntas (una parte del total) y guarda un JSON por pregunta con todo lo medible.

  python scripts/run_agent_batch.py --release R --questions Q.csv --shard 0/3 --out out_0.jsonl --max-usd 0.30
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from regulabank.agents.agentic import AgenticAgent, load_conflicts
from regulabank.agents.llm import load_provider
from regulabank.graphs import embed as embed_mod
from regulabank.retrieval.search import Retriever


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--shard", default="0/1")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-usd", type=float, default=0.30, help="tope de gasto de esta parte: al pasarlo, se detiene")
    a = p.parse_args()
    i, n = (int(x) for x in a.shard.split("/"))
    qs = [q for k, q in enumerate(csv.DictReader(open(a.questions, encoding="utf-8"))) if k % n == i]
    r = Retriever(a.release, embed_mod.load_embedder("openai:text-embedding-3-small", "", 32))
    agent = AgenticAgent(r, load_provider("openai", cache_dir=a.release / "llm-cache"), conflicts=load_conflicts(a.release / "conflicts.parquet"))
    spent = 0.0
    with open(a.out, "w", encoding="utf-8") as fh:
        for q in qs:
            if spent > a.max_usd:
                print(f"tope de gasto alcanzado ({spent:.3f} USD): parte detenida en {q['id']}", flush=True)
                break
            try:
                s = agent.ask(q["pregunta"], "2026-10-17")
            except Exception as exc:  # noqa: BLE001 - un fallo de red no tumba el lote: queda registrado como error
                fh.write(json.dumps({"id": q["id"], "error": f"{type(exc).__name__}: {exc}"[:300]}, ensure_ascii=False) + "\n"); fh.flush()
                continue
            u = s.get("usage", {})
            spent += u.get("cost_usd", 0.0)
            row = {"id": q["id"], "status": s["status"], "risk": s["risk"], "summary": s["summary"], "scenario": s["scenario"],
                   "plan": s.get("plan", {}), "tool_calls": s.get("calls", 0), "fixes": s.get("fixes", 0), "faults": [f["kind"] for f in s.get("faults", [])],
                   "model": u.get("model"), "cost_usd": u.get("cost_usd", 0.0), "latency_ms": s["timings_ms"]["total"], "evidence": s["tb"].evidence,
                   "seen": [h.chunk_id for h in s["tb"].hits],
                   "claims": [{"n": c["n"], "chunk_id": c["chunk_id"], "article_id": r.rows[c["chunk_id"]]["article_id"], "verified": c["verified"],
                               "quote": c["quote"], "text": r.rows[c["chunk_id"]]["text"][:1800], "citation": r.rows[c["chunk_id"]]["citation"]}
                              for c in s.get("claims", [])]}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
            print(f"{q['id']} {s['status']:9s} {s['timings_ms']['total'] / 1000:5.1f}s {u.get('cost_usd', 0):.4f} USD", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
