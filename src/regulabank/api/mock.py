"""Datos de muestra para la maqueta. Textos SINTETICOS con forma de norma; no son el texto oficial.

Cuando exista el release real (docs/02-corpus.md) este modulo se reemplaza por lecturas a Parquet/Lance/Falkor
detras de las mismas funciones.
"""

from __future__ import annotations

from datetime import date

from regulabank.api import contracts as c

# --- normas ----------------------------------------------------------------------------------------------------

_NORMS: dict[str, c.NormSummary] = {
    "pe-sbs-res-2660-2015": c.NormSummary(
        id="pe-sbs-res-2660-2015", short="Res. SBS 2660-2015",
        title="Reglamento de Gestión de Riesgos de Lavado de Activos y del Financiamiento del Terrorismo",
        kind="sbs_resolution", issuer="SBS", published="2015-05-14", status="partial", n_articles=3,
        topics=["LAFT", "cumplimiento"],
    ),
    "pe-sbs-res-11356-2008": c.NormSummary(
        id="pe-sbs-res-11356-2008", short="Res. SBS 11356-2008",
        title="Reglamento para la Evaluación y Clasificación del Deudor y la Exigencia de Provisiones",
        kind="sbs_resolution", issuer="SBS", published="2008-11-19", status="in_force", n_articles=2,
        topics=["riesgo de crédito", "provisiones"],
    ),
    "pe-congreso-ley-26702-1996": c.NormSummary(
        id="pe-congreso-ley-26702-1996", short="Ley 26702",
        title="Ley General del Sistema Financiero y del Sistema de Seguros y Orgánica de la SBS",
        kind="law", issuer="Congreso", published="1996-12-09", status="in_force", n_articles=1,
        topics=["sistema financiero"],
    ),
    "policy-credit-2024": c.NormSummary(
        id="policy-credit-2024", short="Política de Crédito v3",
        title="Política interna de otorgamiento y seguimiento de créditos (sintética)",
        kind="internal_policy", issuer="Banco (sintético)", published="2024-03-01", status="in_force", n_articles=1,
        topics=["riesgo de crédito"],
    ),
    "policy-aml-2023": c.NormSummary(
        id="policy-aml-2023", short="Manual LAFT v2",
        title="Manual interno de prevención de lavado de activos (sintético)",
        kind="internal_policy", issuer="Banco (sintético)", published="2023-09-15", status="in_force", n_articles=1,
        topics=["LAFT"],
    ),
}


def _v(aid: str, n: int, valid_from: str, valid_to: str | None, kind: str, by: str | None, text: str) -> c.Version:
    return c.Version(id=f"{aid}@v{n}", n=n, valid_from=valid_from, valid_to=valid_to, change_kind=kind, changed_by=by, text=text)


_ARTICLES: dict[str, c.Article] = {}


def _article(**kw) -> c.Article:
    kw["current"] = next(v for v in kw["versions"] if v.valid_to is None)
    return c.Article(**kw)


def _add(a: c.Article) -> None:
    _ARTICLES[a.id] = a


_aid = "pe-sbs-res-2660-2015#art-25"
_add(_article(
    id=_aid, norm_id="pe-sbs-res-2660-2015", no="25", path="Capítulo IV > Artículo 25",
    versions=[
        _v(_aid, 1, "2015-05-15", "2019-03-31", "original", None,
           "Artículo 25.- Reporte de operaciones sospechosas. Las empresas deben comunicar a la UIF-Perú las "
           "operaciones sospechosas dentro de los treinta (30) días calendario de detectadas, adjuntando la "
           "documentación de sustento."),
        _v(_aid, 2, "2019-04-01", None, "modified", "pe-sbs-res-1234-2019",
           "Artículo 25.- Reporte de operaciones sospechosas. Las empresas deben comunicar a la UIF-Perú las "
           "operaciones sospechosas dentro de los quince (15) días hábiles de detectadas, adjuntando la "
           "documentación de sustento y el formulario del Anexo N° 6."),
    ],
    refers_to=["pe-sbs-res-2660-2015#art-3"], entities=["UIF-Perú", "operación sospechosa", "15 días hábiles", "Anexo N° 6"],
))
_aid = "pe-sbs-res-2660-2015#art-3"
_add(_article(
    id=_aid, norm_id="pe-sbs-res-2660-2015", no="3", path="Capítulo I > Artículo 3",
    versions=[_v(_aid, 1, "2015-05-15", None, "original", None,
                 "Artículo 3.- Definiciones. Para efectos del presente Reglamento se entiende por: (a) Operación "
                 "sospechosa: aquella operación inusual que, luego del análisis, carece de justificación económica "
                 "aparente. (b) Oficial de Cumplimiento: funcionario responsable de vigilar el sistema de prevención.")],
    entities=["operación sospechosa", "Oficial de Cumplimiento"],
))
_aid = "pe-sbs-res-2660-2015#art-9"
_add(_article(
    id=_aid, norm_id="pe-sbs-res-2660-2015", no="9", path="Capítulo II > Artículo 9",
    versions=[_v(_aid, 1, "2015-05-15", None, "original", None,
                 "Artículo 9.- Registro de operaciones. Las empresas registran las operaciones en efectivo iguales o "
                 "superiores a diez mil dólares americanos (USD 10 000) o su equivalente en moneda nacional.")],
    entities=["USD 10 000", "registro de operaciones"],
))
_aid = "pe-sbs-res-11356-2008#art-4"
_add(_article(
    id=_aid, norm_id="pe-sbs-res-11356-2008", no="4", path="Capítulo I > Artículo 4",
    versions=[_v(_aid, 1, "2008-11-20", None, "original", None,
                 "Artículo 4.- Clasificación crediticia del deudor. El deudor con atraso en el pago entre treinta y "
                 "uno (31) y sesenta (60) días calendario se clasifica en la categoría Con Problemas Potenciales (CPP).")],
    refers_to=["pe-congreso-ley-26702-1996#art-222"], entities=["deudor", "CPP", "60 días"],
))
_aid = "pe-sbs-res-11356-2008#art-12"
_add(_article(
    id=_aid, norm_id="pe-sbs-res-11356-2008", no="12", path="Capítulo II > Artículo 12",
    versions=[_v(_aid, 1, "2008-11-20", None, "original", None,
                 "Artículo 12.- Exposición máxima. La exposición total con un mismo deudor no excederá el diez por "
                 "ciento (10 %) del patrimonio efectivo de la empresa, salvo las excepciones de la Ley General.")],
    refers_to=["pe-congreso-ley-26702-1996#art-222"], entities=["10 %", "patrimonio efectivo"],
))
_aid = "pe-congreso-ley-26702-1996#art-222"
_add(_article(
    id=_aid, norm_id="pe-congreso-ley-26702-1996", no="222", path="Título III > Capítulo I > Artículo 222",
    versions=[_v(_aid, 1, "1996-12-10", None, "original", None,
                 "Artículo 222.- Evaluación de las operaciones que integran la cartera crediticia. La SBS "
                 "reglamenta la clasificación del deudor y la exigencia de provisiones.")],
    entities=["SBS", "provisiones"],
))
_aid = "policy-credit-2024#sec-5.2"
_add(_article(
    id=_aid, norm_id="policy-credit-2024", no="5.2", path="5. Límites > 5.2 Exposición por deudor",
    versions=[_v(_aid, 1, "2024-03-01", None, "original", None,
                 "5.2 La exposición total con un mismo deudor no excederá el doce por ciento (12 %) del patrimonio "
                 "efectivo, previa aprobación del Comité de Riesgos.")],
    entities=["12 %", "Comité de Riesgos"],
))
_aid = "policy-aml-2023#sec-4.1"
_add(_article(
    id=_aid, norm_id="policy-aml-2023", no="4.1", path="4. Reportes > 4.1 Plazo de reporte",
    versions=[_v(_aid, 1, "2023-09-15", None, "original", None,
                 "4.1 El Oficial de Cumplimiento remite el ROS a la UIF-Perú dentro de los veinte (20) días hábiles "
                 "de calificada la operación como sospechosa.")],
    entities=["20 días hábiles", "ROS", "Oficial de Cumplimiento"],
))

_CONFLICTS: list[c.Conflict] = [
    c.Conflict(
        id="cf-001", policy_chunk_id="c_policy_aml_41", policy_citation="Manual LAFT v2, 4.1",
        policy_quote="dentro de los veinte (20) días hábiles",
        norm_version_id="pe-sbs-res-2660-2015#art-25@v2", norm_citation="Res. SBS 2660-2015, art. 25 (vigente desde 2019-04-01)",
        norm_quote="dentro de los quince (15) días hábiles", relation="contradicts", method="rules", score=0.98,
        reason="La política da 20 días hábiles; la norma vigente exige 15. La política cita el plazo de la versión derogada (30 días calendario).",
        status="pending_human",
    ),
    c.Conflict(
        id="cf-002", policy_chunk_id="c_policy_credit_52", policy_citation="Política de Crédito v3, 5.2",
        policy_quote="no excederá el doce por ciento (12 %)",
        norm_version_id="pe-sbs-res-11356-2008#art-12@v1", norm_citation="Res. SBS 11356-2008, art. 12",
        norm_quote="no excederá el diez por ciento (10 %)", relation="contradicts", method="judge", score=0.91,
        reason="Límite interno (12 %) mayor al regulatorio (10 %); la excepción de la Ley General no aplica al caso descrito.",
        status="pending_human",
    ),
]


# --- consultas ---------------------------------------------------------------------------------------------------

def norms() -> list[c.NormSummary]:
    return list(_NORMS.values())


def norm(norm_id: str) -> c.NormDetail | None:
    n = _NORMS.get(norm_id)
    if n is None:
        return None
    arts = [a for a in _ARTICLES.values() if a.norm_id == norm_id]
    return c.NormDetail(**n.model_dump(), articles=arts)


def article(article_id: str) -> c.Article | None:
    return _ARTICLES.get(article_id)


def conflicts() -> list[c.Conflict]:
    return _CONFLICTS


def decide(conflict_id: str, decision: c.Decision) -> c.Conflict | None:
    for cf in _CONFLICTS:
        if cf.id == conflict_id:
            cf.status = "confirmed" if decision.action == "accept" else "dismissed"
            cf.method = "human"
            return cf
    return None


def version_at(a: c.Article, as_of: date) -> c.Version | None:
    for v in a.versions:
        start = date.fromisoformat(v.valid_from)
        end = date.fromisoformat(v.valid_to) if v.valid_to else None
        if start <= as_of and (end is None or as_of <= end):
            return v
    return None


def _cit(a: c.Article, v: c.Version) -> str:
    n = _NORMS[a.norm_id]
    tail = f"vigente desde {v.valid_from}" if v.valid_to is None else f"vigente {v.valid_from} a {v.valid_to}"
    return f"{n.short}, art. {a.no} ({tail})"


def answer(req: c.AnswerRequest) -> c.Answer:
    """Respuesta guionada: elige el articulo por palabras clave y arma claims con cita literal verificada."""
    q = req.question.lower()
    as_of = date.fromisoformat(req.as_of) if req.as_of else date.today()
    thread = req.thread_id or f"t-{abs(hash(req.question)) % 10_000:04d}"
    if "sospechosa" in q or "uif" in q or "ros" in q:
        aid, scenario, quote_key = "pe-sbs-res-2660-2015#art-25", "lookup", "dentro de los"
    elif "exposici" in q or "patrimonio" in q or "mismo deudor" in q:
        aid, scenario, quote_key = "pe-sbs-res-11356-2008#art-12", "threshold", "no excederá"
    elif "cpp" in q or "atraso" in q or "clasific" in q:
        aid, scenario, quote_key = "pe-sbs-res-11356-2008#art-4", "procedure", "se clasifica"
    elif "efectivo" in q or "registr" in q:
        aid, scenario, quote_key = "pe-sbs-res-2660-2015#art-9", "threshold", "iguales o superiores"
    elif "define" in q or "entiende por" in q or "qué es" in q or "que es" in q:
        aid, scenario, quote_key = "pe-sbs-res-2660-2015#art-3", "definition", "se entiende por"
    else:
        return c.Answer(
            thread_id=thread, status="abstained", risk="notify", as_of=as_of.isoformat(),
            summary="No encontré una norma del corpus que fije eso. Lo más cercano está en la Res. SBS 2660-2015 y la Res. SBS 11356-2008.",
            claims=[], history=[],
            trace=c.Trace(scenario="negative", seen=[], lists={"dense": 50, "bm25": 50}, ppr_new=0, faults=[], fixes=0,
                          latency_ms=74, cost_usd=0.0, model="mock", prompt_version="p0"),
        )
    a = _ARTICLES[aid]
    v = version_at(a, as_of) or a.current
    sent = next((s for s in v.text.split(". ") if quote_key in s), v.text)
    quote = sent.strip().rstrip(".")
    claim = c.Claim(
        text=sent.strip(), chunk_id=f"c_{aid.split('#')[1]}_{v.n}", article_id=aid, quote=quote, citation=_cit(a, v),
        valid_from=v.valid_from, valid_to=v.valid_to, verified=quote in v.text,
    )
    history = [c.HistoryItem(article_id=aid, citation=_cit(a, hv), valid_from=hv.valid_from, valid_to=hv.valid_to,
                             change_kind=hv.change_kind, changed_by=hv.changed_by) for hv in a.versions if hv.id != v.id]
    risk: c.RiskLevel = "approve" if v.valid_to is not None else ("notify" if scenario == "threshold" else "auto")
    status: c.AnswerStatus = "pending_human" if risk == "approve" else "ok"
    return c.Answer(
        thread_id=thread, status=status, risk=risk, as_of=as_of.isoformat(),
        summary=f"Según {_cit(a, v)}: {sent.strip()}",
        claims=[claim], history=history,
        trace=c.Trace(scenario=scenario, seen=[claim.chunk_id, "c_art-3_1"], lists={"dense": 50, "bm25": 50, "entities": 12},
                      ppr_new=3, faults=[], fixes=0, latency_ms=81, cost_usd=0.0, model="mock", prompt_version="p0"),
    )
