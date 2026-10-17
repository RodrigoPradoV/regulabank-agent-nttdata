"""Agente con herramientas (ReAct sobre LangGraph): el modelo decide como buscar y cada paso se emite como evento.

  agent -> (tool_calls?) -> tools -> agent ...      el modelo llama search / read / refers_to / neighbors / conflicts
  agent -> (texto final) -> verify -+- ok -> deliver -> ledger
                                    +- faltas, fixes < MAX_FIXES -> fix -> agent
                                    `- faltas, fixes = MAX_FIXES -> reject -> ledger

Todas las herramientas son de solo lectura sobre el release congelado y numeran los fragmentos [n]; el modelo solo puede
citar esos [n]. La verificacion (cada cita existe, cada cifra esta en lo citado, vigencia) es la misma `check` de
answer.py y corre en codigo. Cada nodo devuelve `events`: lo que se transmite al chat para mostrar el trabajo del agente.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterator, TypedDict

import pyarrow.parquet as pq
from langgraph.graph import END, START, StateGraph

from regulabank.agents.answer import MAX_FIXES, NO_EVIDENCE, check, compose, detect_scenario, load_risk, parse_as_of, strip_preamble
from regulabank.agents.llm import Provider
from regulabank.graphs import embed as embed_mod
from regulabank.retrieval.search import Hit, Retriever, verify_quote

MAX_CALLS = 6
PROMPT_VERSION = "agentic-v5"
CALLS_BY_COMPLEXITY = {1: 3, 2: 5, 3: 8}      # presupuesto de herramientas segun la complejidad que el agente se asigna
READ_CLIP = 2400

SYSTEM = """Eres un analista de cumplimiento normativo bancario del Perú. Tienes herramientas de SOLO LECTURA sobre un corpus \
de 17 normas reales (SBS, BCBS, GAFI, UE, decretos). Trabaja así:
0. Tu primer paso es SIEMPRE `plan` (una sola vez): evalúa la complejidad y elige la estrategia.
1. Antes de cada llamada a una herramienta escribe UNA línea corta que diga qué vas a hacer y por qué (el usuario la ve).
2. Empieza siempre con `search`. Si los resultados no alcanzan, reformula y busca otra vez (sinónimos, el término definido, \
el número de la norma); si la pregunta nombra una norma, busca con `norm_id`.
3. Usa `read` para leer el texto completo antes de citar una cifra o un plazo.
4. Usa `refers_to` si el texto remite a otro artículo, `neighbors` si el texto continúa, `conflicts` si preguntan si dos \
normas coinciden o se contradicen.
5. Respeta el presupuesto de llamadas que fijó tu plan. Empiezas con un modelo económico; si la pregunta exige comparar varias normas, \
resolver una contradicción o razonar sobre vigencias entre versiones, llama `escalate` UNA vez (pasa a un modelo más potente y más caro).
6. Responde SOLO con lo que leíste. Cada afirmación termina con su cita [n] (n = número de fragmento que devolvieron las \
herramientas). Toda cifra debe estar en el fragmento citado. Prefiere fragmentos vigentes a la fecha de consulta; uno NO \
vigente úsalo solo para explicar cómo cambió la norma, y dilo.
7. Si no hay sustento, empieza con «No encontré sustento en el corpus» y di en una línea qué es lo más cercano.
Estilo: español natural, como un colega experto que explica a otro: la respuesta directa primero y después el detalle que importa, \
en prosa corrida, sin etiquetas, sin encabezados y sin preámbulo («Buscaré…», «Respuesta directa:»). La respuesta final empieza por la \
respuesta. No digas «fragmento», «pasaje» ni «según el texto»; pon la cita [n] al final de la frase que la usa, sin repetir la pregunta ni \
enumerar. Texto plano, máximo 180 palabras."""

PLAN_TOOL = {"type": "function", "function": {
    "name": "plan",
    "description": ("Evalúa la pregunta antes de buscar. complejidad 1 = dato directo de una norma (plazo, cifra, definición); "
                    "2 = compara normas o versiones, o depende de la vigencia a una fecha; "
                    "3 = multi-salto: la respuesta exige seguir remisiones entre artículos o normas o encadenar varios datos. "
                    "estrategia: direct (1-2 búsquedas), multi_query (reformula en 2-3 búsquedas distintas), "
                    "compare (busca cada norma por separado y usa conflicts), multi_hop (descompón en subpreguntas; "
                    "search, read, refers_to y vuelve a buscar con lo aprendido)."),
    "parameters": {"type": "object", "properties": {
        "complexity": {"type": "integer", "enum": [1, 2, 3]},
        "strategy": {"type": "string", "enum": ["direct", "multi_query", "compare", "multi_hop"]},
        "subquestions": {"type": "array", "items": {"type": "string"}, "description": "hasta 3 subpreguntas, en el orden de resolución"},
        "reason": {"type": "string", "description": "una frase: por qué esta complejidad y esta estrategia"}},
        "required": ["complexity", "strategy", "reason"]}}}

TOOLS = [
    {"type": "function", "function": {
        "name": "search", "description": "Busca fragmentos del corpus por significado. Devuelve fragmentos numerados [n] con su vigencia.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "consulta en español, concreta"},
            "norm_id": {"type": "string", "description": "opcional: limita a una norma (id exacto, p. ej. pe-sbs-res-2660-2015)"},
            "k": {"type": "integer", "description": "cuántos fragmentos (1 a 8)", "default": 6}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read", "description": "Lee el texto completo del fragmento n.",
        "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}},
    {"type": "function", "function": {
        "name": "refers_to", "description": "Fragmentos a los que remite el fragmento n y fragmentos que lo citan.",
        "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}},
    {"type": "function", "function": {
        "name": "neighbors", "description": "El fragmento anterior y el siguiente a n dentro de la misma norma.",
        "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}},
    {"type": "function", "function": {
        "name": "escalate", "description": "Cambia al modelo más potente para el resto de la tarea. Úsala una sola vez y solo si la pregunta lo exige.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "por qué hace falta"}}, "required": ["reason"]}}},
    {"type": "function", "function": {
        "name": "conflicts", "description": "Pares de oraciones donde un modelo NLI detectó contradicción entre el fragmento n y otra norma (sin validar).",
        "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}},
]


def short(h: Hit, rows: dict[str, dict]) -> str:
    return rows[h.chunk_id]["citation"] or h.norm_short


class Toolbox:
    """Herramientas de solo lectura; guarda los fragmentos vistos numerados [n] (el modelo solo puede citar esos)."""

    def __init__(self, retriever: Retriever, as_of: str, conflicts: dict[str, list[dict]] | None = None):
        self.r, self.as_of = retriever, as_of
        self.hits: list[Hit] = []
        self.index: dict[str, int] = {}
        self.conflicts_by_chunk = conflicts or {}
        self.n_search = 0
        self.order = list(retriever.rows)
        self.pos = {c: i for i, c in enumerate(self.order)}

    def register(self, hit: Hit) -> int:
        if hit.chunk_id not in self.index:
            self.hits.append(hit)
            self.index[hit.chunk_id] = len(self.hits)
        return self.index[hit.chunk_id]

    def brief(self, hit: Hit, clip: int = 260) -> dict:
        n = self.register(hit)
        return {"n": n, "norma": hit.norm_short, "cita": short(hit, self.r.rows), "vigente": hit.is_current,
                "desde": hit.valid_from, "hasta": hit.valid_to, "fragmento": " ".join(hit.text.split())[:clip]}

    def _get(self, n: Any) -> Hit | None:
        return self.hits[n - 1] if isinstance(n, int) and 1 <= n <= len(self.hits) else None

    def call(self, name: str, args: dict) -> tuple[dict, dict]:
        """(resultado para el modelo, resumen para la interfaz)."""
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return {"error": f"herramienta desconocida: {name}"}, {"summary": f"herramienta desconocida: {name}", "items": []}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"argumentos inválidos: {exc}"}, {"summary": "argumentos inválidos", "items": []}

    def _items(self, briefs: list[dict]) -> list[dict]:
        return [{"n": b["n"], "cita": b["cita"], "vigente": b["vigente"], "fragmento": b["fragmento"][:160]} for b in briefs]

    def t_search(self, query: str, norm_id: str | None = None, k: int = 6) -> tuple[dict, dict]:
        k = max(1, min(int(k or 6), 8))
        old = self.r.p["top_k"]
        self.r.p["top_k"] = 8
        try:
            res = self.r.search(query, self.as_of, strategy="dense_valid", quotes=False)
        finally:
            self.r.p["top_k"] = old
        hits = [h for h in res.hits if norm_id is None or h.norm_id == norm_id][:k]
        self.n_search += 1
        briefs = [self.brief(h) for h in hits]
        scope = f" en {norm_id}" if norm_id else ""
        return ({"consulta": query, "resultados": briefs},
                {"summary": f"{len(briefs)} fragmentos para «{query}»{scope}", "items": self._items(briefs)})

    def t_read(self, n: int) -> tuple[dict, dict]:
        h = self._get(n)
        if h is None:
            return {"error": f"[{n}] no existe; usa un n devuelto por las herramientas"}, {"summary": f"[{n}] no existe", "items": []}
        b = self.brief(h)
        return ({"n": b["n"], "cita": b["cita"], "vigente": b["vigente"], "texto": " ".join(h.text.split())[:READ_CLIP]},
                {"summary": f"leyó [{n}] {b['cita']}", "items": self._items([b])})

    def t_refers_to(self, n: int) -> tuple[dict, dict]:
        h = self._get(n)
        if h is None:
            return {"error": f"[{n}] no existe"}, {"summary": f"[{n}] no existe", "items": []}
        out, seen = [], set()
        for dst in self.r.refers.get(h.chunk_id, []):
            for cid in self.r.by_article.get(dst, [])[:2]:
                if cid not in seen and cid != h.chunk_id:
                    seen.add(cid); out.append(("remite a", cid))
        for cid in self.r.referrers.get(self.r.rows[h.chunk_id]["article_id"], [])[:3]:
            if cid not in seen and cid != h.chunk_id:
                seen.add(cid); out.append(("citado por", cid))
        briefs = [{**self.brief(self.r.hit(cid, self.as_of)), "relacion": rel} for rel, cid in out[:6]]
        return ({"de": n, "relaciones": briefs},
                {"summary": f"[{n}] tiene {len(briefs)} remisiones", "items": self._items(briefs)})

    def t_neighbors(self, n: int) -> tuple[dict, dict]:
        h = self._get(n)
        if h is None:
            return {"error": f"[{n}] no existe"}, {"summary": f"[{n}] no existe", "items": []}
        i, norm = self.pos[h.chunk_id], h.norm_id
        briefs = []
        for rel, j in (("anterior", i - 1), ("siguiente", i + 1)):
            if 0 <= j < len(self.order) and self.r.rows[self.order[j]]["norm_id"] == norm:
                briefs.append({**self.brief(self.r.hit(self.order[j], self.as_of)), "relacion": rel})
        return ({"de": n, "vecinos": briefs}, {"summary": f"contexto de [{n}]: {len(briefs)} fragmentos", "items": self._items(briefs)})

    def t_conflicts(self, n: int) -> tuple[dict, dict]:
        h = self._get(n)
        if h is None:
            return {"error": f"[{n}] no existe"}, {"summary": f"[{n}] no existe", "items": []}
        rows = sorted(self.conflicts_by_chunk.get(h.chunk_id, []), key=lambda r: -r["p"])[:4]
        briefs, out = [], []
        for r in rows:
            b = self.brief(self.r.hit(r["other"], self.as_of))
            briefs.append(b)
            out.append({"con": b["n"], "cita": b["cita"], "probabilidad": round(r["p"], 3), "esta_oracion": r["mine"][:240],
                        "otra_oracion": r["theirs"][:240], "nota": "NLI sin validar"})
        return ({"de": n, "contradicciones": out},
                {"summary": f"[{n}]: {len(out)} posibles contradicciones (NLI sin validar)", "items": self._items(briefs)})


def load_conflicts(path: Path, p_min: float = 0.9) -> dict[str, list[dict]]:
    """chunk_id -> contradicciones NLI en las que participa (ambos lados)."""
    out: dict[str, list[dict]] = defaultdict(list)
    if not path.exists():
        return out
    for r in pq.read_table(path).to_pylist():
        if r["label"] == "contradiction" and r["p_contradiction"] >= p_min:
            out[r["chunk_a"]].append({"other": r["chunk_b"], "p": r["p_contradiction"], "mine": r["premise"], "theirs": r["hypothesis"]})
            out[r["chunk_b"]].append({"other": r["chunk_a"], "p": r["p_contradiction"], "mine": r["hypothesis"], "theirs": r["premise"]})
    return out


STRATEGY_ES = {"direct": "directa", "multi_query": "varias reformulaciones", "compare": "comparar normas", "multi_hop": "varios saltos"}


def narrate(ev: dict) -> str:
    """Una frase en español por evento, hecha en codigo: la interfaz muestra lo que el agente hace aunque el modelo calle."""
    t = ev["type"]
    if t == "start":
        return f"Entendí la pregunta como «{ev['scenario']}» y consulto la vigencia al {ev['as_of']}."
    if t == "plan":
        subs = f" Subpreguntas: {'; '.join(ev['subquestions'])}." if ev.get("subquestions") else ""
        return (f"Complejidad {ev['complexity']} de 3, estrategia {STRATEGY_ES.get(ev['strategy'], ev['strategy'])}: {ev['reason']}"
                f" Presupuesto de {ev['budget']} consultas con {ev['model']}.{subs}")
    if t == "think":
        return ev["text"]
    if t == "tool":
        a, name = ev.get("args", {}), ev["name"]
        if name == "search":
            return f"Busqué «{a.get('query', '')}»: {ev['summary']}."
        if name == "read":
            return f"Leí el fragmento [{a.get('n')}] completo para citar la cifra exacta."
        if name == "refers_to":
            return f"Seguí las remisiones de [{a.get('n')}]: {ev['summary']}."
        if name == "neighbors":
            return f"Miré el contexto de [{a.get('n')}]: {ev['summary']}."
        if name == "conflicts":
            return f"Revisé contradicciones de [{a.get('n')}]: {ev['summary']}."
        if name == "escalate":
            return f"Pedí un modelo más potente: {a.get('reason', '')}."
        return ev["summary"]
    if t == "model":
        return f"Cambio de {ev.get('from')} a {ev['to']}: {ev.get('reason', '')}."
    if t == "draft":
        return "Redacté la respuesta con lo que leí."
    if t == "verify":
        if ev["ok"]:
            return "Verifiqué cada cita y cada cifra contra el texto: todo coincide."
        return f"La verificación encontró {len(ev['faults'])} faltas ({'; '.join(f[:70] for f in ev['faults'][:2])}); la corrijo."
    if t == "deliver":
        return {"ok": f"Entrego la respuesta con {ev.get('claims', 0)} citas verificadas.",
                "abstained": "No hay sustento en el corpus: me abstengo en vez de inventar.",
                "pending_human": f"Entrego la respuesta con {ev.get('claims', 0)} citas; queda pendiente de aprobación humana.",
                "rejected": "No pude pasar la verificación de citas; entrego solo las fuentes."}.get(ev.get("status", ""), "Entregué la respuesta.")
    return ""


class State(TypedDict, total=False):
    question: str
    as_of: str
    thread_id: str
    scenario: str
    tb: Toolbox
    messages: list[dict]
    hits: list[Hit]
    text: str
    faults: list[dict]
    fixes: int
    calls: int
    usage: dict
    events: list[dict]
    status: str
    risk: str
    claims: list[dict]
    summary: str
    timings_ms: dict
    lists: dict
    ppr_new: int
    mean6: float | None
    model: str
    plan: dict
    max_calls: int


@dataclass
class AgenticAgent:
    retriever: Retriever
    provider: Provider
    risk_rules: dict[str, str] = field(default_factory=load_risk)
    conflicts: dict[str, list[dict]] = field(default_factory=dict)
    ledger_path: Path | None = None

    def __post_init__(self) -> None:
        self.models = self.provider.models()          # de menor a mayor potencia

    # ---- nodos ---------------------------------------------------------------------------------------------
    def plan(self, s: State) -> State:
        """Primer paso obligatorio: el modelo se asigna una complejidad y una estrategia; la complejidad fija el presupuesto de
        herramientas y el modelo (3 = el potente desde el inicio). Corre con el modelo economico."""
        reply = self.provider.chat(s["messages"], [PLAN_TOOL], PROMPT_VERSION, model=self.models[0],
                                   tool_choice={"type": "function", "function": {"name": "plan"}})
        msg = reply.message
        u = dict(s.get("usage", {}))
        u.update(tokens_in=u.get("tokens_in", 0) + reply.tokens_in, tokens_out=u.get("tokens_out", 0) + reply.tokens_out,
                 cost_usd=round(u.get("cost_usd", 0.0) + reply.cost_usd, 6), model=reply.model, calls=u.get("calls", 0) + 1)
        tcs = msg.get("tool_calls") or []
        try:
            args = json.loads(tcs[0]["function"]["arguments"]) if tcs else {}
        except (json.JSONDecodeError, KeyError):
            args = {}
        complexity = args.get("complexity") if args.get("complexity") in (1, 2, 3) else 2
        plan = {"complexity": complexity, "strategy": args.get("strategy") or "direct",
                "subquestions": [str(x) for x in (args.get("subquestions") or [])][:3], "reason": args.get("reason", "")}
        model = self.models[-1] if complexity == 3 else self.models[0]
        msgs = list(s["messages"]) + [msg] if tcs else list(s["messages"])
        if tcs:
            msgs.append({"role": "tool", "tool_call_id": tcs[0]["id"], "content": json.dumps(
                {"plan_registrado": plan, "presupuesto_de_herramientas": CALLS_BY_COMPLEXITY[complexity], "modelo": model}, ensure_ascii=False)})
        events = [{"type": "plan", **plan, "budget": CALLS_BY_COMPLEXITY[complexity], "model": model}]
        return {"messages": msgs, "plan": plan, "model": model, "max_calls": CALLS_BY_COMPLEXITY[complexity], "usage": u, "events": events}

    def agent(self, s: State) -> State:
        tools = TOOLS if s["calls"] < s.get("max_calls", MAX_CALLS) else None
        reply = self.provider.chat(s["messages"], tools, PROMPT_VERSION, model=s.get("model"))
        u = dict(s.get("usage", {}))
        u.update(tokens_in=u.get("tokens_in", 0) + reply.tokens_in, tokens_out=u.get("tokens_out", 0) + reply.tokens_out,
                 cost_usd=round(u.get("cost_usd", 0.0) + reply.cost_usd, 6), model=reply.model, finish_reason=reply.finish_reason,
                 calls=u.get("calls", 0) + 1, cached=u.get("cached", 0) + int(getattr(reply, "cached", False)))
        msg = reply.message
        events = []
        if msg.get("tool_calls"):
            if msg.get("content"):
                events.append({"type": "think", "text": msg["content"], "model": reply.model})
        else:
            events.append({"type": "draft", "text": strip_preamble(msg.get("content") or ""), "model": reply.model})
        return {"messages": s["messages"] + [msg], "usage": u, "events": events, "text": strip_preamble(msg.get("content") or "") if not msg.get("tool_calls") else ""}

    def after_agent(self, s: State) -> str:
        return "tools" if s["messages"][-1].get("tool_calls") else "verify"

    def tools(self, s: State) -> State:
        tb, msgs, events = s["tb"], list(s["messages"]), []
        calls, model = s["calls"], s.get("model")
        for tc in s["messages"][-1]["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "escalate":
                strong = self.models[-1]
                if model == strong:
                    result, ui = {"modelo": model, "nota": "ya usas el más potente"}, {"summary": "ya usa el modelo más potente", "items": []}
                else:
                    events.append({"type": "model", "from": model, "to": strong, "reason": args.get("reason", "")})
                    model = strong
                    result, ui = {"modelo": model}, {"summary": f"cambia a {model}: {args.get('reason', '')}", "items": []}
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, ensure_ascii=False)})
                events.append({"type": "tool", "name": name, "args": args, "summary": ui["summary"], "items": [], "call": calls})
                continue
            if calls >= s.get("max_calls", MAX_CALLS):
                result, ui = {"error": "límite de llamadas alcanzado: responde con lo que ya leíste"}, {"summary": "límite de llamadas", "items": []}
            else:
                result, ui = tb.call(name, args)
                calls += 1
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, ensure_ascii=False)})
            events.append({"type": "tool", "name": name, "args": args, "summary": ui["summary"], "items": ui["items"], "call": calls})
        return {"messages": msgs, "calls": calls, "hits": tb.hits, "events": events, "model": model}

    def verify(self, s: State) -> State:
        tb, text = s["tb"], s["text"]
        faults = check(text, tb.hits, s["scenario"], s["as_of"], s.get("usage", {}).get("finish_reason"))
        if tb.n_search == 0:
            faults.append({"kind": "no_search", "detail": "no usaste `search`: busca en el corpus antes de responder"})
        if not text.strip():
            faults.append({"kind": "empty", "detail": "respuesta vacía"})
        return {"faults": faults, "events": [{"type": "verify", "ok": not faults, "attempt": s.get("fixes", 0) + 1,
                                              "faults": [f"{f['kind']}: {f['detail']}" for f in faults]}]}

    def after_verify(self, s: State) -> str:
        if not s["faults"]:
            return "deliver"
        return "fix" if s.get("fixes", 0) < MAX_FIXES else "reject"

    def fix(self, s: State) -> State:
        note = "Tu respuesta tuvo estas faltas; corrígelas (puedes usar más herramientas). Responde SOLO con la respuesta final, sin preámbulo ni explicar qué cambiaste:\n" + "\n".join(
            f"- {f['kind']}: {f['detail']}" for f in s["faults"])
        strong, events = self.models[-1], []
        if s.get("model") != strong:
            events.append({"type": "model", "from": s.get("model"), "to": strong, "reason": "la verificación encontró faltas"})
        return {"messages": s["messages"] + [{"role": "user", "content": note}], "fixes": s.get("fixes", 0) + 1,
                "events": events, "model": strong}

    def deliver(self, s: State) -> State:
        """Citas literales: para cada fragmento citado, la oracion con mayor coseno a la pregunta (tramo verificado)."""
        tb, text = s["tb"], s["text"]
        if not text.startswith(NO_EVIDENCE):
            qvec = embed_mod.embed_query(s["question"], self.retriever.embedder)
            for n in {int(x) for x in re.findall(r"\[(\d+)\]", text)}:
                if 1 <= n <= len(tb.hits):
                    h = tb.hits[n - 1]
                    q = self.retriever.own_quote(qvec, h.text)
                    row = self.retriever.rows[h.chunk_id]
                    h.quote, h.quote_verified, h.citation = q, verify_quote(q, h.text), self.retriever.cite(row, q)
        out = compose(text, tb.hits, s["scenario"], self.risk_rules)
        return {**out, "events": [{"type": "deliver", "status": out["status"], "risk": out["risk"], "claims": len(out["claims"])}]}

    def reject(self, s: State) -> State:
        tb = s["tb"]
        lines = [f"[{i}] {short(h, self.retriever.rows)}" for i, h in enumerate(tb.hits[:3], 1)]
        text = "No pude redactar una respuesta que pase la verificación de citas. Fuentes más relevantes:\n" + "\n".join(lines)
        return {"status": "rejected", "risk": "approve", "claims": [], "summary": text,
                "events": [{"type": "deliver", "status": "rejected", "risk": "approve", "claims": 0}]}

    def ledger(self, s: State) -> State:
        row = {"thread_id": s["thread_id"], "question": s["question"], "scenario": s["scenario"], "as_of": s["as_of"],
               "status": s["status"], "risk": s["risk"], "seen": [h.chunk_id for h in s["tb"].hits], "tool_calls": s["calls"],
               "faults": [f["kind"] for f in s.get("faults", [])], "fixes": s.get("fixes", 0), **s.get("usage", {}),
               "prompt_version": PROMPT_VERSION}
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"events": []}

    def graph(self):
        g = StateGraph(State)
        for name in ("plan", "agent", "tools", "verify", "fix", "deliver", "reject", "ledger"):
            g.add_node(name, getattr(self, name))
        g.add_edge(START, "plan")
        g.add_edge("plan", "agent")
        g.add_conditional_edges("agent", self.after_agent, {"tools": "tools", "verify": "verify"})
        g.add_edge("tools", "agent")
        g.add_conditional_edges("verify", self.after_verify, {"deliver": "deliver", "fix": "fix", "reject": "reject"})
        g.add_edge("fix", "agent")
        g.add_edge("deliver", "ledger")
        g.add_edge("reject", "ledger")
        g.add_edge("ledger", END)
        return g.compile()

    # ---- ejecucion -----------------------------------------------------------------------------------------
    def run(self, question: str, as_of: str | None = None, thread_id: str | None = None) -> Iterator[tuple[str, Any]]:
        """Genera ("event", dict) por cada paso y al final ("state", estado final)."""
        t0 = time.perf_counter()
        as_of = as_of or parse_as_of(question, date.today().isoformat())
        tb = Toolbox(self.retriever, as_of, self.conflicts)
        scenario = detect_scenario(question)
        state: dict = {"question": question, "as_of": as_of, "thread_id": thread_id or uuid.uuid4().hex[:12], "scenario": scenario,
                       "tb": tb, "model": self.models[0], "plan": {}, "max_calls": MAX_CALLS, "calls": 0, "fixes": 0, "faults": [], "usage": {}, "hits": [], "lists": {}, "ppr_new": 0, "mean6": None,
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": f"Fecha de consulta: {as_of}\nPregunta: {question}"}]}
        start = {"type": "start", "thread_id": state["thread_id"], "question": question, "as_of": as_of, "scenario": scenario, "ms": 0}
        yield "event", {**start, "say": narrate(start)}
        for update in self.graph().stream(state, stream_mode="updates"):
            for node, upd in update.items():
                state.update(upd or {})
                for ev in (upd or {}).get("events", []):
                    yield "event", {**ev, "node": node, "ms": round((time.perf_counter() - t0) * 1000), "say": narrate(ev)}
        state["timings_ms"] = {"total": round((time.perf_counter() - t0) * 1000)}
        yield "state", state

    def ask(self, question: str, as_of: str | None = None, thread_id: str | None = None) -> State:
        final: State = {}
        for kind, payload in self.run(question, as_of, thread_id):
            if kind == "state":
                final = payload
        return final
