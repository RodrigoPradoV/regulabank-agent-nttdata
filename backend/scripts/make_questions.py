"""40 preguntas del CORPUS REAL para validar el agente: 34 con respuesta (salen de chunks reales) y 6 negativas (a mano).

  python scripts/make_questions.py --release RELEASE --out docs/eval/Preguntas_40_corpus.csv

Positivas: dos chunks por norma (17 normas = 34), elegidos con semilla fija entre los de 500 a 1.600 caracteres, sin revision pendiente y sin
rastros de extraccion rota; la mitad prefiere chunks con cifras o plazos (lo interesante de citar). Para cada chunk gpt-5-mini escribe UNA pregunta
natural y autocontenida que ese chunk responde, su tipo y 1 a 3 datos clave copiados literalmente del chunk. Es una etiqueta *silver* (la escribe
un modelo): lo que se mide contra ella es mecanico (¿el agente cito ese articulo?) y lo juzga un modelo de otra familia.
Negativas: las seis del golden hechas a mano, sobre temas que el corpus no cubre.
"""

import argparse
import csv
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.agents.llm import load_provider
from regulabank.retrieval.search import clean_text

NEGATIVES = [
    "¿Cuál es la tasa máxima que fija la SBS para créditos hipotecarios?",
    "¿Qué tasa del Impuesto a las Transacciones Financieras se aplica a los retiros en efectivo?",
    "¿Qué requisitos exige la normativa para operar una plataforma de financiamiento participativo financiero?",
    "¿Cuál es la tasa de encaje mínimo legal en moneda extranjera que exige el BCRP?",
    "¿Qué plazo máximo fija la normativa para un contrato de arrendamiento financiero?",
    "¿Qué establece la normativa peruana sobre criptoactivos en banca?",
]
SYSTEM = ("Escribes preguntas de prueba para un asistente de normativa bancaria. Dado un fragmento de una norma, escribe UNA pregunta que ese "
          "fragmento responde, natural y autocontenida (nombra la norma o el tema; no digas «el fragmento»), sin copiar sus frases. Devuelve SOLO JSON: "
          '{"pregunta": "...", "tipo": "plazo_cifra|definicion|obligacion|condicion_excepcion|procedimiento", "datos_clave": ["1 a 3 datos copiados literalmente del fragmento"]}')
NOISY = re.compile(r"[-\x00]|\bfi [a-záéíóúñ]{2,}|►M\d|▼")


def pick(rows: list[dict], seed: int) -> list[dict]:
    rng = random.Random(seed)
    ok = [r for r in rows if 500 <= len(r["text"]) <= 1600 and not r["review_required"] and not NOISY.search(r["text"])
          and r["node_type"] in ("article", "numbered_section", "numeral", "recommendation", "section", "principle", "standard_section")]
    by_norm: dict[str, list[dict]] = {}
    for r in ok:
        by_norm.setdefault(r["norm_id"], []).append(r)
    out = []
    for norm in sorted(by_norm):
        cand = by_norm[norm]
        with_num = [r for r in cand if re.search(r"\d+\s*(horas|días|dias|%|por ciento|UIT|US\$|S/|años|meses)", r["text"])]
        first = rng.choice(with_num or cand)
        rest = [r for r in cand if r["article_id"] != first["article_id"]]
        out.append(first)
        rng.shuffle(rest)
        out.extend(rest[:4])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=11)
    a = p.parse_args()
    rows = [{**r, "text": clean_text(r["text"])} for r in pq.read_table(a.release / "chunks.parquet").to_pylist()]
    chosen = pick(rows, a.seed)
    # primero 2 por norma (los dos primeros de cada grupo), el resto de reserva por si el modelo no devuelve JSON valido
    per: dict[str, list[dict]] = {}
    for r in chosen:
        per.setdefault(r['norm_id'], []).append(r)
    chosen = [r for g in per.values() for r in g[:2]] + [r for g in per.values() for r in g[2:]]
    provider = load_provider("openai", cache_dir=a.release / "llm-cache")

    def ask(r: dict) -> dict:
        reply = provider.chat([{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": f"[{r['citation']}]\n{' '.join(r['text'].split())}"}], None, "questions-v1", model="gpt-5-mini")
        try:
            d = json.loads(re.sub(r"^```(?:json)?|```$", "", (reply.message.get("content") or "").strip(), flags=re.M).strip())
        except json.JSONDecodeError:
            d = {}
        return {"chunk": r, "d": d, "cost": reply.cost_usd}

    with ThreadPoolExecutor(4) as ex:
        made = list(ex.map(ask, chosen[:44]))
    out = []
    for m in made:
        d, r = m["d"], m["chunk"]
        if not d.get("pregunta"):
            continue
        out.append({"id": "", "tipo": d.get("tipo", ""), "negativa": 0, "pregunta": " ".join(d["pregunta"].split()), "norma": r["norm_short"],
                    "source_chunk_id": r["chunk_id"], "source_article_id": r["article_id"], "fuente": r["citation"],
                    "datos_clave": " | ".join(d.get("datos_clave", []))})
    out = out[:34]       # los primeros por norma ya vienen primero; los de reserva solo completan
    for q in NEGATIVES:
        out.append({"id": "", "tipo": "negativa", "negativa": 1, "pregunta": q, "norma": "", "source_chunk_id": "", "source_article_id": "", "fuente": "", "datos_clave": ""})
    for i, q in enumerate(out, 1):
        q["id"] = f"p{i:02d}"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} preguntas ({sum(1 - q['negativa'] for q in out)} positivas, {sum(q['negativa'] for q in out)} negativas), costo {sum(m['cost'] for m in made):.4f} USD -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
