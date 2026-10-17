"""Califica las respuestas del agente con un criterio simple y definido y calcula metricas de confiabilidad.

  python scripts/score_answers.py prepare --questions Q.csv --batches 'batch_*.jsonl' --out-dir DIR      # arma las entradas del juez (2 partes)
  python scripts/score_answers.py report  --questions Q.csv --batches 'batch_*.jsonl' --judged 'DIR/judged_*.jsonl' --out docs/eval/Respuestas_40_preguntas_corpus_validadas

CRITERIO (cada respuesta con respuesta de verdad vale 0 o 1; una respuesta CONFIABLE cumple los cuatro):
  citas        (codigo)  hay al menos una cita y todas son un tramo literal verificado del chunk
  fuente       (codigo)  cita el articulo del que salio la pregunta
  respaldo     (juez)    toda afirmacion de la respuesta esta en los textos citados
  responde     (juez)    contesta lo que la pregunta pide
En una pregunta NEGATIVA (el corpus no la cubre) la respuesta es confiable si el agente se abstiene; si afirma algo, es una alucinacion.
Metrica de cabecera: % de las 40 respuestas confiables. El juez es un modelo de otra familia que el que responde (y ve solo la respuesta y los textos citados).
`fuente` y `dato_clave` se miden contra una etiqueta silver (la pregunta la escribio un modelo desde ese chunk): se reportan aparte y no entran al titular.
"""

import argparse
import csv
import glob
import json
import random
import statistics
import sys
from pathlib import Path


def load(questions: Path, batches: str) -> tuple[list[dict], dict[str, dict]]:
    qs = list(csv.DictReader(open(questions, encoding="utf-8")))
    runs: dict[str, dict] = {}
    for f in sorted(glob.glob(batches)):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            runs[r["id"]] = r
    return qs, runs


def prepare(a) -> None:
    qs, runs = load(a.questions, a.batches)
    items = []
    for q in qs:
        r = runs.get(q["id"])
        if not r or "error" in r or r["status"] == "abstained":
            continue          # abstenciones y errores no se juzgan: no afirman nada
        items.append({"id": q["id"], "pregunta": q["pregunta"], "negativa": int(q["negativa"]), "datos_clave": q["datos_clave"],
                      "respuesta": r["summary"], "citas": [{"n": c["n"], "cita": c["citation"], "texto": c["text"]} for c in r["claims"]]})
    a.out_dir.mkdir(parents=True, exist_ok=True)
    half = (len(items) + 1) // 2
    for k, part in enumerate((items[:half], items[half:])):
        (a.out_dir / f"judge_in_{k}.json").write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} respuestas a juzgar en 2 partes -> {a.out_dir}")


def boot(vals: list[float], n: int = 4000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    ms = sorted(statistics.fmean(rng.choices(vals, k=len(vals))) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def report(a) -> None:
    qs, runs = load(a.questions, a.batches)
    judged = {}
    for f in sorted(glob.glob(a.judged)):
        for line in open(f, encoding="utf-8"):
            if line.strip().startswith("{"):
                j = json.loads(line)
                judged[j["id"]] = j
    rows = []
    for q in qs:
        r = runs.get(q["id"]) or {"status": "sin_corrida", "claims": [], "summary": ""}
        neg = int(q["negativa"])
        status = r["status"]
        citas = int(bool(r["claims"]) and all(c["verified"] for c in r["claims"])) if status != "abstained" else None
        fuente = int(any(c["article_id"] == q["source_article_id"] for c in r["claims"])) if not neg and status != "abstained" else None
        j = judged.get(q["id"], {})
        respaldo, responde, clave = j.get("respaldo"), j.get("responde"), j.get("dato_clave")
        if neg:
            ok = int(status == "abstained")
        elif status == "abstained":
            ok = 0                                    # abstencion falsa: la norma si la responde
        else:
            ok = int(bool(citas) and respaldo == 1 and responde == 1) if j else None
        rows.append({"id": q["id"], "tipo": q["tipo"], "negativa": neg, "pregunta": q["pregunta"], "estado": status, "citas_verificadas": citas, "cita_el_articulo_de_origen": fuente,
                     "respaldo_juez": respaldo, "responde_juez": responde, "dato_clave_juez": clave, "confiable": ok, "respuesta": r["summary"].replace("\n", " "),
                     "notas_juez": j.get("notas", ""), "fuente_esperada": q["fuente"], "consultas": r.get("tool_calls"), "modelo": r.get("model"),
                     "costo_usd": r.get("cost_usd"), "segundos": round(r["latency_ms"] / 1000, 1) if r.get("latency_ms") else None, "evidencia": r.get("evidence")})
    scored = [r for r in rows if r["confiable"] is not None]
    pos = [r for r in rows if not r["negativa"]]
    neg = [r for r in rows if r["negativa"]]
    answered_pos = [r for r in pos if r["estado"] not in ("abstained", "sin_corrida")]
    m = {"n": len(rows), "con_corrida": sum(1 for r in rows if r["estado"] != "sin_corrida"), "juzgadas": len(scored)}
    vals = [float(r["confiable"]) for r in scored]
    m["confiables_pct"] = round(100 * statistics.fmean(vals), 1) if vals else None
    m["confiables_ic95_pct"] = [round(100 * x, 1) for x in boot(vals)] if len(vals) > 3 else None
    rate = lambda rs, k: round(100 * statistics.fmean(r[k] for r in rs if r[k] is not None), 1) if any(r[k] is not None for r in rs) else None  # noqa: E731
    m["positivas"] = {"n": len(pos), "confiables_pct": rate(pos, "confiable"), "respondidas": len(answered_pos), "abstenciones_falsas": sum(r["estado"] == "abstained" for r in pos),
                      "citas_verificadas_pct": rate(answered_pos, "citas_verificadas"), "respaldo_pct": rate(answered_pos, "respaldo_juez"), "responde_pct": rate(answered_pos, "responde_juez"),
                      "cita_el_articulo_de_origen_pct": rate(answered_pos, "cita_el_articulo_de_origen"), "dato_clave_pct": rate(answered_pos, "dato_clave_juez")}
    asked_neg = [r for r in neg if r["estado"] != "abstained"]
    m["negativas"] = {"n": len(neg), "se_abstuvo_pct": round(100 * (len(neg) - len(asked_neg)) / len(neg), 1) if neg else None, "alucinaciones": len(asked_neg),
                      "ids_que_afirmaron": [r["id"] for r in asked_neg]}
    judged_answers = [r for r in rows if r["respaldo_juez"] is not None]
    m["alucinacion_pct_de_lo_respondido"] = round(100 * statistics.fmean(1 - r["respaldo_juez"] for r in judged_answers), 1) if judged_answers else None
    lat = sorted(r["segundos"] for r in rows if r["segundos"])
    m["costo_total_usd"] = round(sum(r["costo_usd"] or 0 for r in rows), 4)
    m["segundos"] = {"p50": lat[len(lat) // 2] if lat else None, "p95": lat[int(0.95 * (len(lat) - 1))] if lat else None}
    by_type: dict[str, list[float]] = {}
    for r in scored:
        by_type.setdefault(r["tipo"], []).append(float(r["confiable"]))
    m["por_tipo_confiables_pct"] = {k: [round(100 * statistics.fmean(v), 1), len(v)] for k, v in sorted(by_type.items())}
    m["fallas"] = [{"id": r["id"], "tipo": r["tipo"], "estado": r["estado"], "motivo": r["notas_juez"] or ("abstencion falsa" if r["estado"] == "abstained" and not r["negativa"] else "")}
                   for r in scored if not r["confiable"]]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out) + ".csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    Path(str(out) + ".json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "report"):
        s = sub.add_parser(name)
        s.add_argument("--questions", type=Path, required=True)
        s.add_argument("--batches", required=True)
        if name == "prepare":
            s.add_argument("--out-dir", type=Path, required=True)
        else:
            s.add_argument("--judged", required=True)
            s.add_argument("--out", required=True)
    a = p.parse_args()
    prepare(a) if a.cmd == "prepare" else report(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
