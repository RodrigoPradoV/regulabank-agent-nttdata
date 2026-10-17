"""Agrega `data/ledger/answer_graph.jsonl` para el dashboard de trazabilidad.

Cubre el Componente 6 (auditoria) y 7 (tiempo ahorrado) de `docs/ALCANCE_Y_REQUISITOS_FUNCIONALES.md`, y la fila
"costo y latencia: USD y ms por consulta, p50/p95 | ledger" de `docs/10-evaluation.md`. Puro: lee el ledger ya
escrito por `graph.py`, nunca lo modifica (append-only).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from regulabank.agents.ledger import DEFAULT_LEDGER_PATH
from regulabank.agents.ledger import read_all as read_entries

# Promedio de la columna "Tiempo Humano" de los 7 casos U-1..U-7 (docs/ALCANCE_Y_REQUISITOS_FUNCIONALES.md,
# seccion 5): 225 min / 7 = ~32 min. Sin una linea base por escenario todavia, se usa este promedio unico y se
# declara como estimado en la API/UI; solo se aplica a consultas resueltas solas (`ok`/`abstained`), nunca a las
# que necesitaron revision humana o terminaron rechazadas, donde el ahorro no es claro.
HUMAN_BASELINE_MINUTES = 32.0
_AUTONOMOUS_STATUSES = {"ok", "abstained"}


@dataclass(frozen=True)
class MetricsFilters:
    date_from: str | None = None  # compara contra `logged_at` (ISO), inclusive
    date_to: str | None = None
    scenario: str | None = None
    status: str | None = None
    risk: str | None = None
    model: str | None = None
    q: str | None = None  # texto libre, buscado en `question`


def _matches(entry: dict[str, Any], f: MetricsFilters) -> bool:
    logged_at = entry.get("logged_at") or ""
    if f.date_from and logged_at < f.date_from:
        return False
    if f.date_to and logged_at[:10] > f.date_to[:10]:  # por dia completo: `date_to` incluye toda esa fecha
        return False
    if f.scenario and entry.get("scenario") != f.scenario:
        return False
    if f.status and entry.get("status") != f.status:
        return False
    if f.risk and entry.get("risk") != f.risk:
        return False
    if f.model and entry.get("model") != f.model:
        return False
    if f.q and f.q.lower() not in (entry.get("question") or "").lower():
        return False
    return True


def filter_entries(entries: list[dict[str, Any]], filters: MetricsFilters) -> list[dict[str, Any]]:
    return [e for e in entries if _matches(e, filters)]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(entries)
    latencies = [float(e["latency_ms"]) for e in entries if isinstance(e.get("latency_ms"), (int, float))]
    approve_total = sum(1 for e in entries if e.get("risk") == "approve")

    fault_counts: Counter[str] = Counter()
    for e in entries:
        fault_counts.update(e.get("faults") or [])

    saved_minutes = sum(
        max(HUMAN_BASELINE_MINUTES - (e.get("latency_ms") or 0) / 60_000, 0.0)
        for e in entries if e.get("status") in _AUTONOMOUS_STATUSES and e.get("risk") != "approve"
    )

    return {
        "total": total,
        "by_status": dict(Counter(e.get("status") or "desconocido" for e in entries)),
        "by_risk": dict(Counter(e.get("risk") or "sin_riesgo" for e in entries)),
        "by_scenario": dict(Counter(e.get("scenario") or "desconocido" for e in entries)),
        "fault_counts": dict(fault_counts),
        "fixes_histogram": dict(Counter(str(e.get("fixes", 0)) for e in entries)),
        "human_review_rate": (approve_total / total) if total else 0.0,
        "latency_ms_avg": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "latency_ms_p50": _percentile(latencies, 0.5),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "time_saved_minutes": saved_minutes,
        "human_baseline_minutes": HUMAN_BASELINE_MINUTES,
    }


def daily_series(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        day = (e.get("logged_at") or "desconocido")[:10]
        buckets.setdefault(day, []).append(e)

    series = []
    for day in sorted(buckets):
        rows = buckets[day]
        latencies = [float(r["latency_ms"]) for r in rows if isinstance(r.get("latency_ms"), (int, float))]
        series.append({
            "bucket": day,
            "count": len(rows),
            "latency_ms_avg": (sum(latencies) / len(latencies)) if latencies else 0.0,
            "abstained": sum(1 for r in rows if r.get("status") == "abstained"),
            "rejected": sum(1 for r in rows if r.get("status") == "rejected"),
        })
    return series


def load(path: Path = DEFAULT_LEDGER_PATH) -> list[dict[str, Any]]:
    return read_entries(path)
