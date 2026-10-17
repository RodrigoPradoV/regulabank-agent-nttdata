"""`grade`: confianza de la evidencia recuperada, antes de redactar (docs/09-agents.md, estilo CRAG).

Puro, con umbrales desde `seeds/params.toml` (nunca en el prompt). Decide si hay evidencia suficiente
(`ok`), ambigua (`ambiguous`, pasa por `judge_evidence`) o nula (`no_evidence`, se abstiene) -- y ademas
devuelve el numero crudo (`evidence.mean6`) para mostrarlo en la UI, no solo la categoria.
"""

from __future__ import annotations

from regulabank.agents.contracts import GradeResult, Hit
from regulabank.agents.params import load_params


def grade(hits: list[Hit], params: dict | None = None) -> GradeResult:
    params = params if params is not None else load_params()
    thresholds = params.get("grade", {})
    rescue_floor = thresholds.get("rescue_floor", 0.08)
    ambiguous_floor = thresholds.get("ambiguous_floor", 0.2)

    top6 = hits[:6]
    mean6 = sum(h.score for h in top6) / len(top6) if top6 else 0.0

    if not hits or mean6 < rescue_floor:
        label = "no_evidence"
    elif mean6 < ambiguous_floor:
        label = "ambiguous"
    else:
        label = "ok"
    return GradeResult(label=label, score=round(mean6, 4))
