"""NLI en GPU (RunPod) sobre pares de oraciones: `joeddav/xlm-roberta-large-xnli`.

  python pod/nli.py --pairs nli_pairs.parquet --out out_nli --preflight     # 2 pares + el mas largo, proyeccion
  python pod/nli.py --pairs nli_pairs.parquet --out out_nli                 # corrida completa, reanudable
  python pod/nli.py --pairs nli_pairs.parquet --out out_nli --limit 20 --allow-cpu   # humo en la Mac

Autocontenido: solo torch, transformers, sentencepiece y pyarrow (el paquete regulabank no se sube).
Reglas (lecciones pagadas): aborta sin CUDA salvo `--allow-cpu`; `max_length` explicito y tokens truncados contados;
lotes atomicos y reanudables por `pair_id`; un lote que falla se reintenta par por par y el par malo queda con
label `error` (la corrida sigue); `DONE` solo si todos los pares tienen resultado; entrada vacia es valida.

Entrada: columnas pair_id, premise, hypothesis. Salida: out/nli_scores.parquet con pair_id, p_contradiction,
p_neutral, p_entailment, label, error; out/manifest.json; out/DONE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

MODEL = "joeddav/xlm-roberta-large-xnli"
MAX_LENGTH = 256   # tokens por par (premisa + hipotesis); el modelo admite 512
SCHEMA = pa.schema([
    ("pair_id", pa.string()), ("p_contradiction", pa.float32()), ("p_neutral", pa.float32()),
    ("p_entailment", pa.float32()), ("label", pa.string()), ("error", pa.string()),
])


def atomic_write(table: pa.Table, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def pick_device(allow_cpu: bool) -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if not allow_cpu:
        sys.exit("ABORT: torch.cuda.is_available() es False y no se paso --allow-cpu (este job cuesta por hora)")
    return "mps" if torch.backends.mps.is_available() else "cpu"


class Nli:
    def __init__(self, device: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch, self.device = torch, device
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL).to(device).eval()
        self.labels = {int(i): l.lower() for i, l in self.model.config.id2label.items()}
        missing = {"contradiction", "neutral", "entailment"} - set(self.labels.values())
        if missing:
            sys.exit(f"ABORT: {MODEL} no trae las etiquetas NLI esperadas; faltan {sorted(missing)}")

    def predict(self, premises: list[str], hypotheses: list[str]) -> tuple[list[dict[str, float]], int]:
        enc = self.tok(premises, hypotheses, truncation=True, max_length=MAX_LENGTH, padding=True,
                       return_tensors="pt")
        full = self.tok(premises, hypotheses, truncation=False)["input_ids"]
        truncated = sum(len(x) > MAX_LENGTH for x in full)
        enc = enc.to(self.device)
        with self.torch.no_grad():
            probs = self.torch.softmax(self.model(**enc).logits.float(), dim=-1).cpu().numpy()
        return [{self.labels[j]: float(p[j]) for j in range(len(p))} for p in probs], truncated


def row(pair_id: str, pr: dict[str, float] | None, error: str | None = None) -> dict:
    if pr is None:
        return {"pair_id": pair_id, "p_contradiction": None, "p_neutral": None, "p_entailment": None,
                "label": "error", "error": error}
    return {"pair_id": pair_id, "p_contradiction": pr["contradiction"], "p_neutral": pr["neutral"],
            "p_entailment": pr["entailment"], "label": max(pr, key=pr.get), "error": None}


def score_batch(nli: Nli, rows: list[dict]) -> tuple[list[dict], int]:
    """Un lote; si falla se reintenta par por par y el par malo queda como error sin tumbar la corrida."""
    try:
        probs, trunc = nli.predict([r["premise"] for r in rows], [r["hypothesis"] for r in rows])
        return [row(r["pair_id"], p) for r, p in zip(rows, probs)], trunc
    except Exception:  # noqa: BLE001 - se aisla el par que rompe
        out, trunc = [], 0
        for r in rows:
            try:
                probs, t = nli.predict([r["premise"]], [r["hypothesis"]])
                out.append(row(r["pair_id"], probs[0]))
                trunc += t
            except Exception as exc:  # noqa: BLE001
                out.append(row(r["pair_id"], None, f"{type(exc).__name__}: {exc}"[:300]))
        return out, trunc


def read_pairs(path: Path) -> pa.Table:
    table = pq.read_table(path)
    missing = [c for c in ("pair_id", "premise", "hypothesis") if c not in table.schema.names]
    if missing:
        sys.exit(f"ABORT: {path} sin columnas {missing}")
    return table.select(["pair_id", "premise", "hypothesis"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pairs", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("out_nli"))
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--allow-cpu", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=32)
    args = p.parse_args(argv)

    pairs = read_pairs(args.pairs)
    if args.limit:
        pairs = pairs.slice(0, args.limit)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    n = pairs.num_rows
    if n == 0:
        atomic_write(pa.Table.from_pylist([], schema=SCHEMA), out / "nli_scores.parquet")
        (out / "DONE").write_text("empty\n")
        print("entrada vacia: nada que juzgar", flush=True)
        return 0
    device = pick_device(args.allow_cpu)
    t0 = time.perf_counter()
    nli = Nli(device)
    load_s = time.perf_counter() - t0
    rows = pairs.to_pylist()

    if args.preflight:
        longest = max(range(n), key=lambda i: len(rows[i]["premise"]) + len(rows[i]["hypothesis"]))
        sample = [rows[i] for i in sorted({0, min(1, n - 1), longest})]
        t0 = time.perf_counter()
        scored, trunc = score_batch(nli, sample)
        per = (time.perf_counter() - t0) / len(sample)
        print(f"preflight: {len(sample)} pares en {device} (mas largo: "
              f"{len(rows[longest]['premise']) + len(rows[longest]['hypothesis'])} caracteres, truncados {trunc})")
        print(f"  carga {load_s:.1f} s | {per:.3f} s/par | proyeccion {per * n:.0f} s para {n} pares")
        for r in scored:
            print("  ", r["label"], r["p_contradiction"], r["error"])
        return 1 if any(r["label"] == "error" for r in scored) else 0

    parts = out / "parts"
    parts.mkdir(exist_ok=True)
    done: dict[str, dict] = {}
    for f in sorted(parts.glob("nli.*.parquet")):
        for r in pq.read_table(f).to_pylist():
            done[r["pair_id"]] = r
    pending = [r for r in rows if r["pair_id"] not in done]
    print(f"{len(done)} hechos, {len(pending)} pendientes en {device}", flush=True)
    next_n, truncated, t0 = len(list(parts.glob("nli.*.parquet"))), 0, time.perf_counter()
    for i in range(0, len(pending), args.batch_size):
        batch = pending[i:i + args.batch_size]
        scored, trunc = score_batch(nli, batch)
        truncated += trunc
        atomic_write(pa.Table.from_pylist(scored, schema=SCHEMA), parts / f"nli.{next_n + i // args.batch_size:05d}.parquet")
        for r in scored:
            done[r["pair_id"]] = r
        el = time.perf_counter() - t0
        print(f"[nli] {len(done)}/{n} pares | {(i + len(batch)) / el * 60:.0f} pares/min | {el:.0f} s", flush=True)
    final = [done[r["pair_id"]] for r in rows]
    errors = sum(r["label"] == "error" for r in final)
    atomic_write(pa.Table.from_pylist(final, schema=SCHEMA), out / "nli_scores.parquet")
    labels: dict[str, int] = {}
    for r in final:
        labels[r["label"]] = labels.get(r["label"], 0) + 1
    manifest = {"model": MODEL, "max_length": MAX_LENGTH, "device": device, "pairs": n, "labels": labels,
                "errors": errors, "truncated_pairs": truncated, "seconds": round(time.perf_counter() - t0, 1),
                "pairs_sha256": hashlib.sha256(args.pairs.read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if errors:
        print(f"FALLO: {errors} pares con error; no se escribe DONE", flush=True)
        return 1
    (out / "DONE").write_text("ok\n")
    print("DONE", json.dumps(manifest), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
