"""Calibra la regla de distancia (evidence_floor) con las corridas reales y mide que haria.

  python scripts/calibrate_floor.py --questions Q.csv --batches 'batch_*.jsonl' [--write seeds/params.toml]

evidencia = mejor promedio del coseno de los 6 fragmentos mas cercanos entre todas las busquedas del agente; distancia = 1 - evidencia.
Umbral = percentil 5 de la evidencia de las positivas de DESARROLLO (un tercio de las positivas, id con resto 0 al dividir por 3, queda
reservado y no entra al calculo). Asi, por construccion, la regla pierde ~5 % de las preguntas respondibles; se reporta cuantas negativas
atrapa sola y cuanto separa (AUC).
"""

import argparse
import csv
import glob
import json
import re
import sys

import numpy as np


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--questions", required=True)
    p.add_argument("--batches", required=True)
    p.add_argument("--write", default=None)
    a = p.parse_args()
    qs = {q["id"]: q for q in csv.DictReader(open(a.questions, encoding="utf-8"))}
    ev = {}
    for f in glob.glob(a.batches):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if "evidence" in r:
                ev[r["id"]] = r["evidence"]
    pos = [k for k, q in qs.items() if not int(q["negativa"]) and k in ev]
    neg = [k for k, q in qs.items() if int(q["negativa"]) and k in ev]
    reserved = [k for k in pos if int(k[1:]) % 3 == 0]
    dev = [k for k in pos if k not in reserved]
    floor = float(np.percentile([ev[k] for k in dev], 5))
    auc = np.mean([(ev[p_] > ev[n_]) + 0.5 * (ev[p_] == ev[n_]) for p_ in pos for n_ in neg])
    out = {"umbral_evidencia": round(floor, 4), "distancia_maxima": round(1 - floor, 4), "auc": round(float(auc), 3),
           "positivas_desarrollo_perdidas": f"{sum(ev[k] < floor for k in dev)}/{len(dev)}",
           "positivas_reservadas_perdidas": f"{sum(ev[k] < floor for k in reserved)}/{len(reserved)}",
           "negativas_atrapadas_por_la_regla": f"{sum(ev[k] < floor for k in neg)}/{len(neg)}",
           "evidencia_positivas": {"min": round(min(ev[k] for k in pos), 3), "mediana": round(float(np.median([ev[k] for k in pos])), 3)},
           "evidencia_negativas": {k: round(ev[k], 3) for k in neg}}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if a.write:
        s = open(a.write, encoding="utf-8").read()
        s = re.sub(r"\nevidence_floor = .*", "", s)
        s = s.rstrip("\n") + (f"\n# Calibrado 2026-10-17 con 40 preguntas reales (docs/eval): percentil 5 de {len(dev)} positivas de desarrollo; AUC {out['auc']};"
                              f" atrapa {out['negativas_atrapadas_por_la_regla']} negativas sola, pierde {out['positivas_reservadas_perdidas']} reservadas.\n"
                              f"evidence_floor = {round(floor, 4)}\n")
        open(a.write, "w", encoding="utf-8").write(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
