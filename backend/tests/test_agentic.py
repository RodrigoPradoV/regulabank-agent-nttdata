"""Ciclo del agente con herramientas, sin red ni modelo real: proveedor guionado y un retriever minimo."""

import json
from types import SimpleNamespace

from regulabank.agents.agentic import AgenticAgent
from regulabank.agents.llm import FakeProvider
from regulabank.graphs.embed import FakeEmbedder
from regulabank.retrieval.search import Hit, verify_quote

TEXT = "El reporte debe remitirse dentro de 24 horas desde que la operación es calificada como sospechosa."
ROWS = {
    "c1": {"chunk_id": "c1", "norm_id": "n1", "norm_short": "Res. A", "article_id": "n1#a1", "article_no": "1", "parent_path": "Art. 1",
           "text": TEXT, "citation": "Res. A, art. 1, p. 1", "valid_from": "2020-01-01", "valid_to": None, "page_start": 1},
    "c2": {"chunk_id": "c2", "norm_id": "n1", "norm_short": "Res. A", "article_id": "n1#a2", "article_no": "2", "parent_path": "Art. 2",
           "text": "Artículo siguiente sin plazos.", "citation": "Res. A, art. 2, p. 1", "valid_from": "2020-01-01", "valid_to": None, "page_start": 1},
}


class StubRetriever:
    rows = ROWS
    refers = {"c1": ["n1#a2"]}
    by_article = {"n1#a1": ["c1"], "n1#a2": ["c2"]}
    referrers: dict = {}
    p = {"top_k": 8, "quote_max_chars": 320}
    embedder = FakeEmbedder()

    def hit(self, cid, as_of, score=0.0, quote=None):
        row = ROWS[cid]
        q = quote or row["text"][:320]
        return Hit(chunk_id=cid, norm_id=row["norm_id"], norm_short=row["norm_short"], article_no=row["article_no"], path=row["parent_path"],
                   citation=f"«{q}» {{{row['citation']}}}", text=row["text"], quote=q, quote_verified=verify_quote(q, row["text"]),
                   score=score, sources={}, valid_from=row["valid_from"], valid_to=None, is_current=True)

    def search(self, query, as_of, strategy="dense_valid", quotes=False):
        return SimpleNamespace(hits=[self.hit("c1", as_of, 1.0)])

    def own_quote(self, qvec, text):
        return text

    def cite(self, row, quote):
        return f"«{quote}» {{{row['citation']}}}"


def call(name, args, i=1):
    return {"id": f"t{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def msg(content=None, *calls):
    m = {"role": "assistant", "content": content}
    if calls:
        m["tool_calls"] = list(calls)
    return m


def agent(script):
    return AgenticAgent(StubRetriever(), FakeProvider(script_msgs=script))  # type: ignore[arg-type]


def kinds(a, q="¿Cuál es el plazo para reportar una operación sospechosa?"):
    events, final = [], None
    for k, p in a.run(q, "2026-10-17"):
        events.append(p) if k == "event" else None
        final = p if k == "state" else final
    return events, final


def test_ciclo_completo_plan_busca_responde_verifica_entrega():
    a = agent([msg(None, call("plan", {"complexity": 1, "strategy": "direct", "reason": "dato directo"})),
               msg("Busco el plazo.", call("search", {"query": "plazo reporte operación sospechosa"}, 2)),
               msg("El plazo es de 24 horas [1].")])
    events, final = kinds(a)
    assert [e["type"] for e in events] == ["start", "plan", "think", "tool", "draft", "verify", "deliver"]
    assert events[1]["complexity"] == 1 and events[1]["budget"] == 3 and events[1]["model"] == "fake-mini"
    assert events[3]["name"] == "search" and events[3]["items"][0]["n"] == 1
    assert final["status"] == "ok" and final["claims"][0]["verified"] and final["summary"].endswith("[1].")


def test_complejidad_3_empieza_con_el_modelo_potente_y_mas_presupuesto():
    a = agent([msg(None, call("plan", {"complexity": 3, "strategy": "multi_hop", "subquestions": ["a", "b"], "reason": "encadena"})),
               msg(None, call("search", {"query": "x"}, 2)), msg("Son 24 horas [1].")])
    events, final = kinds(a)
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["model"] == "fake-strong" and plan["budget"] == 8 and plan["subquestions"] == ["a", "b"]


def test_primera_falla_se_corrige_con_el_mismo_modelo():
    a = agent([msg(None, call("plan", {"complexity": 1, "strategy": "direct", "reason": "r"})),
               msg(None, call("search", {"query": "x"}, 2)),
               msg("El plazo es de 48 horas [1]."),                       # cifra inventada
               msg("El plazo es de 24 horas [1].")])
    events, final = kinds(a)
    types = [e["type"] for e in events]
    assert types.count("verify") == 2 and "model" not in types
    assert final["status"] == "ok" and final["fixes"] == 1 and final["model"] == "fake-mini"


def test_segunda_falla_escala_de_modelo():
    a = agent([msg(None, call("plan", {"complexity": 1, "strategy": "direct", "reason": "r"})),
               msg(None, call("search", {"query": "x"}, 2)),
               msg("El plazo es de 48 horas [1]."), msg("El plazo es de 72 horas [1]."),
               msg("El plazo es de 24 horas [1].")])
    events, final = kinds(a)
    ev = next(e for e in events if e["type"] == "model")
    assert ev["to"] == "fake-strong" and final["status"] == "ok" and final["fixes"] == 2


def test_sin_buscar_no_se_acepta_respuesta():
    a = agent([msg(None, call("plan", {"complexity": 1, "strategy": "direct", "reason": "r"})), msg("Son 24 horas [1]."),
               msg(None, call("search", {"query": "x"}, 2)), msg("Son 24 horas [1].")])
    events, final = kinds(a)
    first = next(e for e in events if e["type"] == "verify")
    assert not first["ok"] and any("no_search" in f for f in first["faults"])
    assert final["status"] == "ok"


def test_herramientas_leen_vecinos_y_escalate():
    a = agent([msg(None, call("plan", {"complexity": 2, "strategy": "compare", "reason": "r"})),
               msg(None, call("search", {"query": "x"}, 2)),
               msg(None, call("read", {"n": 1}, 3), call("neighbors", {"n": 1}, 4), call("escalate", {"reason": "compara"}, 5)),
               msg("Son 24 horas [1].")])
    events, final = kinds(a)
    tools = [e for e in events if e["type"] == "tool"]
    assert [t["name"] for t in tools] == ["search", "read", "neighbors", "escalate"]
    assert any(e["type"] == "model" for e in events)
    assert final["calls"] == 3                       # escalate no gasta presupuesto
