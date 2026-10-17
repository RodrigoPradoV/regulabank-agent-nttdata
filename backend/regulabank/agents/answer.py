"""`answer_graph`: pregunta -> respuesta en texto con cita verificada (docs/09-agents.md, version minima).

LangGraph orquesta; no decide. El modelo entra en UN nodo (`answer`); todo lo demas es codigo y se prueba sin grafo.

  read -> retrieve -> grade -+- no_evidence -------------------------------> abstain -> ledger
                             `- ok -> answer -> verify -+- ok -> deliver -> ledger
                                          ^             +- fail (fixes < MAX_FIXES) -> answer (con las faltas)
                                          `-------------`- fail (fixes = MAX_FIXES) -> reject -> ledger

Quien decide en cada nodo: read, retrieve, grade, verify, deliver, ledger = codigo; answer = modelo (texto plano con
citas [n]). La estrategia de recuperacion (dense | hybrid | hybrid_hop) la elige `route` por escenario, con la tabla
`seeds/route.csv`, que sale de medir en el golden (scripts/eval_agent.py), no de una preferencia.
"""

from __future__ import annotations

import csv
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from regulabank.agents.llm import FakeProvider, Provider
from regulabank.retrieval.search import Hit, Retriever

MAX_FIXES = 2
PROMPT_VERSION = "answer-v1"
CLIP = 1100          # caracteres de cada fragmento en el prompt
NO_EVIDENCE = "No encontré sustento en el corpus"
SEEDS = Path(__file__).resolve().parents[2] / "seeds"

MESES = {m: i for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
MESES["setiembre"] = 9
RX_DATE = re.compile(r"(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de(?:l)?\s+(\d{4})", re.I)

# Escenario por reglas (docs/08): el primero que coincide. `negative` no se detecta aqui: lo decide `grade`.
SCENARIO_RULES: list[tuple[str, re.Pattern]] = [
    ("impact", re.compile(r"qu[eé] (documentos|pol[ií]ticas|procedimientos).*(afect|toca|revis|derogaci|entre en vigencia)", re.I)),
    ("policy_vs_norm", re.compile(r"\b(respeta|cumple|coincide|es consistente|consistente con|de acuerdo con)\b", re.I)),
    ("validity", re.compile(r"(est[aá] vigente|estaba vigente|vigente (al|el|hoy|desde)|se reclasificaba|reemplazar[aá]|desde el \d|aplica hoy|"
                            r"al \d{1,2} de|el \d{1,2} de \w+ de \d{4})", re.I)),
    ("crossref", re.compile(r"qu[eé] (norma|art[ií]culo|circular|reglamento).*(sustent|cita|reemplaza|deroga)", re.I)),
    ("procedure", re.compile(r"qu[eé] pasos|c[oó]mo (calcula|se calcula|se remite|funciona)|procedimiento", re.I)),
    ("definition", re.compile(r"qu[eé] (es|se entiende)|c[oó]mo define|se define", re.I)),
    ("threshold", re.compile(r"cu[aá]nt[oa]s?|qu[eé] (tasa|ratio|porcentaje|l[ií]mite|plazo|colch[oó]n)|cu[aá]l es (el|la) (ratio|tasa|l[ií]mite|plazo)", re.I)),
]


class Fault(TypedDict):
    kind: str
    detail: str


class State(TypedDict, total=False):
    question: str
    as_of: str
    thread_id: str
    scenario: str
    strategy: str
    hits: list[Hit]
    mean6: float | None
    grade: Literal["ok", "no_evidence"]
    text: str
    faults: list[Fault]
    fixes: int
    risk: Literal["auto", "notify", "approve"]
    status: Literal["ok", "abstained", "rejected", "pending_human"]
    claims: list[dict]
    summary: str
    usage: dict
    timings_ms: dict
    lists: dict[str, int]
    ppr_new: int


def detect_scenario(question: str) -> str:
    for name, rx in SCENARIO_RULES:
        if rx.search(question):
            return name
    return "lookup"


def parse_as_of(question: str, default: str) -> str:
    """Una sola fecha explicita en la pregunta («al 1 de febrero de 2027») fija `as_of`; con varias o ninguna, `default`."""
    found = {date(int(y), MESES[m.lower()], int(d)).isoformat() for d, m, y in RX_DATE.findall(question)}
    return found.pop() if len(found) == 1 else default


def load_route(path: Path = SEEDS / "route.csv") -> dict[str, str]:
    """scenario -> strategy (dato medido). Sin archivo, hybrid para todo."""
    if not path.exists():
        return {}
    return {r["scenario"]: r["strategy"] for r in csv.DictReader(open(path, encoding="utf-8"))}


def load_risk(path: Path = SEEDS / "risk_rules.csv") -> dict[str, str]:
    if not path.exists():
        return {}
    return {r["scenario"]: r["level"] for r in csv.DictReader(open(path, encoding="utf-8"))}


def norm_number(s: str) -> str:
    return s.replace(" ", "").replace(",", ".").rstrip(".")


def numbers_in(text: str) -> set[str]:
    """Cifras del texto; «10 000» (espacio como separador de miles) cuenta como 10000."""
    text = text.replace("\u00a0", " ")
    out = {norm_number(x) for x in re.findall(r"\d{1,3}(?: \d{3})+(?:,\d+)?", text)}
    return out | {norm_number(x) for x in re.findall(r"\d+(?:[.,]\d+)*", text)}


def split_claims(text: str) -> list[tuple[str, list[int]]]:
    """Oraciones del texto con los [n] que citan."""
    out = []
    for sent in re.split(r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ¿«(0-9\-•*])|\n+", text):
        cites = [int(n) for n in re.findall(r"\[(\d+)\]", sent)]
        if sent.strip():
            out.append((sent.strip(), cites))
    return out


@dataclass
class AnswerAgent:
    retriever: Retriever
    provider: Provider
    route: dict[str, str] = field(default_factory=load_route)
    risk_rules: dict[str, str] = field(default_factory=load_risk)
    default_strategy: str = "hybrid"
    mean6_floor: float | None = None
    ledger_path: Path | None = None

    # ---- nodos (funciones normales) -----------------------------------------------------------------------
    def read(self, s: State) -> State:
        scenario = detect_scenario(s["question"])
        as_of = s.get("as_of") or parse_as_of(s["question"], date.today().isoformat())
        return {"scenario": scenario, "as_of": as_of, "strategy": self.route.get(scenario, self.default_strategy),
                "faults": [], "fixes": 0, "timings_ms": {}}

    def retrieve(self, s: State) -> State:
        t = time.perf_counter()
        res = self.retriever.search(s["question"], s["as_of"], strategy=s["strategy"])
        ms = dict(s.get("timings_ms", {}), retrieve=round((time.perf_counter() - t) * 1000))
        return {"hits": res.hits, "mean6": res.trace.evidence_mean6, "timings_ms": ms,
                "lists": {k: len(v) for k, v in res.trace.lists.items()}, "ppr_new": len(res.trace.ppr_new)}

    def grade(self, s: State) -> State:
        """Evidencia suficiente por `mean6` (umbral calibrado en el golden; sin umbral, siempre ok)."""
        if not s["hits"] or (self.mean6_floor is not None and (s["mean6"] or 0) < self.mean6_floor):
            return {"grade": "no_evidence"}
        return {"grade": "ok"}

    def answer(self, s: State) -> State:
        hits = s["hits"]
        frag = []
        for i, h in enumerate(hits, 1):
            vig = "vigente" if h.is_current else f"NO vigente a {s['as_of']}"
            span = f"desde {h.valid_from}" + (f" hasta {h.valid_to}" if h.valid_to else "") if h.valid_from else "sin fecha"
            frag.append(f"[{i}] {h.citation.split('{')[-1].rstrip('}').split(' | ')[0]} ({vig}, {span})\n{' '.join(h.text.split())[:CLIP]}")
        system = (
            "Eres un analista de cumplimiento normativo bancario del Perú. Responde SOLO con los fragmentos dados. "
            "Cada afirmación termina con su cita [n]. Prefiere fragmentos vigentes a la fecha de consulta; un fragmento "
            "NO vigente úsalo solo para explicar cómo cambió la norma, y dilo. Si una política interna y una norma se "
            "contradicen, dilo citando ambas. No inventes normas, artículos ni cifras: toda cifra debe estar en el "
            f"fragmento que citas. Si los fragmentos no responden la pregunta, empieza con «{NO_EVIDENCE}» y di en una "
            "línea qué es lo más cercano. Español, texto plano, máximo 150 palabras.")
        user = f"Fecha de consulta: {s['as_of']}\nPregunta: {s['question']}\n\nFragmentos:\n" + "\n\n".join(frag)
        if s.get("faults"):
            user += "\n\nTu respuesta anterior tuvo estas faltas; corrígelas:\n" + "\n".join(
                f"- {f['kind']}: {f['detail']}" for f in s["faults"])
        reply = self.provider.complete(system, user, PROMPT_VERSION)
        u = dict(s.get("usage", {}))
        u["tokens_in"] = u.get("tokens_in", 0) + reply.tokens_in
        u["tokens_out"] = u.get("tokens_out", 0) + reply.tokens_out
        u["cost_usd"] = round(u.get("cost_usd", 0.0) + reply.cost_usd, 6)
        u["model"] = reply.model
        u["finish_reason"] = reply.finish_reason
        u["calls"] = u.get("calls", 0) + 1
        return {"text": reply.text, "usage": u, "fixes": s.get("fixes", 0) + (1 if s.get("faults") else 0)}

    def verify(self, s: State) -> State:
        """Todo en codigo: cada [n] existe, cada cifra esta en lo citado, no se cita lo no vigente sin decirlo."""
        text, hits, faults = s["text"], s["hits"], []
        if finish := s.get("usage", {}).get("finish_reason"):
            if finish == "length":
                faults.append({"kind": "truncated", "detail": "la respuesta se cortó por longitud"})
        if text.startswith(NO_EVIDENCE):
            return {"faults": faults}
        claims = split_claims(text)
        cited = {n for _, cs in claims for n in cs}
        if not cited:
            faults.append({"kind": "no_citation", "detail": "ninguna afirmación lleva cita [n]"})
        for n in sorted(cited):
            if not 1 <= n <= len(hits):
                faults.append({"kind": "foreign_citation", "detail": f"[{n}] no es un fragmento dado"})
        for sent, cs in claims:
            nums = numbers_in(re.sub(r"\[\d+\]", "", sent))
            if not nums or not cs:
                continue
            ok_nums: set[str] = set()
            for n in cs:
                if 1 <= n <= len(hits):
                    h = hits[n - 1]
                    ok_nums |= numbers_in(h.text) | numbers_in(f"{h.valid_from or ''} {h.valid_to or ''} {h.article_no or ''}")
            missing = sorted(x for x in nums if x not in ok_nums and not (x.isdigit() and len(x) == 4 and x in s["as_of"]))
            if missing:
                faults.append({"kind": "foreign_fact", "detail": f"cifras {missing} no están en lo citado: «{sent[:90]}»"})
        stale = [n for n in cited if 1 <= n <= len(hits) and not hits[n - 1].is_current]
        if stale and s["scenario"] not in ("validity", "impact") and not re.search(
                r"no vigente|sustituid|derogad|reemplaz|modificad|anterior|hasta el|dejó", text, re.I):
            faults.append({"kind": "stale_citation", "detail": f"cita fragmentos no vigentes a {s['as_of']}: {stale}"})
        return {"faults": faults}

    def after_verify(self, s: State) -> str:
        if not s["faults"]:
            return "deliver"
        return "answer" if s.get("fixes", 0) < MAX_FIXES else "reject"

    def after_grade(self, s: State) -> str:
        return "abstain" if s["grade"] == "no_evidence" else "answer"

    def _risk(self, s: State, cited: set[int]) -> str:
        level = self.risk_rules.get(s["scenario"], "auto")
        if any(1 <= n <= len(s["hits"]) and not s["hits"][n - 1].is_current for n in cited) and s["scenario"] not in ("validity",):
            level = "approve"
        return level

    def deliver(self, s: State) -> State:
        text = s["text"]
        if text.startswith(NO_EVIDENCE):
            return {"status": "abstained", "risk": "auto", "claims": [], "summary": text}
        sentences = split_claims(text)
        cited = {n for _, cs in sentences for n in cs}
        # Una cita por fragmento, numerada 1..k en el orden en que aparece; el texto se reescribe con esos numeros.
        order: dict[int, int] = {}
        claims: list[dict] = []
        for sent, cs in sentences:
            for n in cs:
                if not 1 <= n <= len(s["hits"]):
                    continue
                if n not in order:
                    order[n] = len(order) + 1
                    h = s["hits"][n - 1]
                    claims.append({"text": re.sub(r"\s*\[\d+\]", "", sent), "chunk_id": h.chunk_id, "n": order[n], "quote": h.quote,
                                   "citation": h.citation, "valid_from": h.valid_from, "valid_to": h.valid_to,
                                   "is_current": h.is_current, "verified": h.quote_verified})
        summary = re.sub(r"\[(\d+)\]", lambda m: f"[{order[int(m.group(1))]}]" if int(m.group(1)) in order else "", text)
        risk = self._risk(s, cited)
        return {"summary": summary, "claims": claims, "risk": risk,
                "status": "pending_human" if risk == "approve" else "ok"}

    def abstain(self, s: State) -> State:
        best = s["hits"][0].citation if s.get("hits") else None
        text = f"{NO_EVIDENCE}: no hay una norma ni política que responda eso." + (f" Lo más cercano: {best}" if best else "")
        return {"status": "abstained", "risk": "auto", "claims": [], "summary": text, "text": text}

    def reject(self, s: State) -> State:
        """Dos intentos con faltas: no se entrega redaccion libre, solo las fuentes verificadas (plantilla)."""
        lines = [f"[{i}] {h.citation}" for i, h in enumerate(s["hits"][:3], 1)]
        text = "No pude redactar una respuesta que pase la verificación de citas. Fuentes más relevantes:\n" + "\n".join(lines)
        return {"status": "rejected", "risk": "approve", "claims": [], "summary": text}

    def ledger(self, s: State) -> State:
        row = {"thread_id": s["thread_id"], "question": s["question"], "scenario": s["scenario"], "strategy": s["strategy"],
               "as_of": s["as_of"], "status": s["status"], "risk": s["risk"], "seen": [h.chunk_id for h in s.get("hits", [])],
               "faults": [f["kind"] for f in s.get("faults", [])], "fixes": s.get("fixes", 0), "mean6": s.get("mean6"),
               **{k: v for k, v in s.get("usage", {}).items()}, "timings_ms": s.get("timings_ms", {}),
               "prompt_version": PROMPT_VERSION}
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {}

    # ---- grafo -------------------------------------------------------------------------------------------
    def graph(self):
        g = StateGraph(State)
        for name in ("read", "retrieve", "grade", "answer", "verify", "deliver", "abstain", "reject", "ledger"):
            g.add_node(name, getattr(self, name))
        g.add_edge(START, "read")
        g.add_edge("read", "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", self.after_grade, {"abstain": "abstain", "answer": "answer"})
        g.add_edge("answer", "verify")
        g.add_conditional_edges("verify", self.after_verify, {"deliver": "deliver", "answer": "answer", "reject": "reject"})
        for end in ("deliver", "abstain", "reject"):
            g.add_edge(end, "ledger")
        g.add_edge("ledger", END)
        return g.compile()

    def ask(self, question: str, as_of: str | None = None, thread_id: str | None = None) -> State:
        t = time.perf_counter()
        out = self.graph().invoke({"question": question, "as_of": as_of or "", "thread_id": thread_id or uuid.uuid4().hex[:12]})
        out["timings_ms"] = dict(out.get("timings_ms", {}), total=round((time.perf_counter() - t) * 1000))
        return out
