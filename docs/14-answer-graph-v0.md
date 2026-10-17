# 14 · `answer_graph` v0: lo construido, el diagrama real y una limitación conocida

Primera implementación del grafo 1 de `09-agents.md` (`answer_graph`), corriendo de punta a punta contra
`data/corpus_v0` real. Vive en `backend/regulabank/agents/`; 47 tests en `backend/tests/` (`pytest`).

## Qué está construido vs. qué es un reemplazo temporal

| Pieza | Estado | Archivo |
|---|---|---|
| `read` (escenario + pesos de canal) | **real**, por regex | `agents/route.py` |
| `grade` (confianza: categoría + número) | **real**, con umbrales en `seeds/params.toml` | `agents/grade.py` |
| `verify` (cita literal, vigencia, números ajenos, lenguaje) | **real**, código puro | `agents/verify.py` |
| `risk` (tabla de reglas) | **real**, `seeds/risk_rules.csv` | `agents/risk.py` |
| `ledger` (una línea por consulta) | **real**, JSONL append-only | `agents/ledger.py` |
| El grafo (`StateGraph`, bucle de reintento, `interrupt` humano) | **real** | `agents/graph.py` |
| `retrieve` | **provisional**: BM25-lexical simple (solape de palabras), sin embeddings ni grafo todavía | `agents/retrieve_stub.py` |
| `answer` / `judge_evidence` (el modelo) | **provisional**: `FakeProvider` guionado, sin LLM real | `agents/providers.py` |

`retrieve_stub` y `FakeProvider` se reemplazan sin tocar ningún otro nodo del grafo: la forma de salida
(`list[Hit]`, `Answer`) no cambia, solo cómo se llena. Son intencionalmente los únicos dos componentes que
dependen de un modelo entrenado.

## Limitación conocida (encontrada probándolo, no teórica)

`FakeProvider.answer()` es deliberadamente simple: toma la primera oración del mejor `Hit` como cita. Cuando el
`retrieve_stub` (lexical puro, sin IDF) devuelve como "mejor" un chunk con ruido de extracción del PDF —por
ejemplo un número de página o un fragmento de encabezado suelto—, la cita sale literal (pasa `verify`, porque
de verdad está en el chunk) pero no es útil. Se vio en vivo con la pregunta *"¿Cuál es el plazo máximo para
remitir el reporte de operaciones sospechosas?"*:

```
escenario=threshold grade=label='ambiguous' score=0.1124 risk=notify
cita [c_d66199ad59ac5502]: '19\nR.'
```

No es un bug de `verify` ni del grafo: ambos componentes involucrados (`retrieve_stub`, `FakeProvider`) son
placeholders declarados como tales. Pero es la prueba concreta de por qué el retrieval real (denso + BM25 +
PPR, `08-retrieval.md`) y un proveedor real importan antes de confiar en esto para una demo — el síntoma
desaparece con mejor retrieval (el chunk ya no sería "el mejor") y con un proveedor que redacte de verdad en
vez de recortar la primera oración.

## El grafo, generado por código (`draw_mermaid()`, no dibujado a mano)

Según el principio ya fijado en `09-agents.md` ("`draw_mermaid()` genera el diagrama; no se dibuja a mano"),
esto es la salida real de `build_answer_graph(FakeProvider()).get_graph().draw_mermaid()` sobre el grafo tal
como está compilado hoy — no una ilustración aparte que se pueda desincronizar del código:

```mermaid
graph TD;
	__start__([<p>__start__</p>]):::first
	read(read)
	retrieve(retrieve)
	grade(grade)
	judge_evidence(judge_evidence)
	answer(answer)
	retry(retry)
	verify(verify)
	risk(risk)
	human(human)
	deliver(deliver)
	abstain(abstain)
	rejected(rejected)
	archive(archive)
	ledger(ledger)
	__end__([<p>__end__</p>]):::last
	__start__ --> read;
	abstain --> ledger;
	answer --> verify;
	archive --> ledger;
	deliver --> ledger;
	grade -.-> abstain;
	grade -.-> answer;
	grade -.-> judge_evidence;
	human -.-> archive;
	human -.-> deliver;
	human -.-> verify;
	judge_evidence --> answer;
	read --> retrieve;
	rejected --> ledger;
	retrieve --> grade;
	retry --> answer;
	risk -.-> deliver;
	risk -.-> human;
	verify -.-> rejected;
	verify -.-> retry;
	verify -.-> risk;
	ledger --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Líneas punteadas = rama condicional (`add_conditional_edges`); líneas sólidas = paso fijo. Para regenerarlo
tras cambiar el grafo:

```python
from regulabank.agents.graph import build_answer_graph
from regulabank.agents.providers import FakeProvider

print(build_answer_graph(FakeProvider()).get_graph().draw_mermaid())
```

## Quién decide en cada nodo (igual que `09-agents.md`, confirmado contra la implementación)

| Nodo | Quién decide | Archivo |
|---|---|---|
| `read` | código (regex) | `route.py` |
| `retrieve` | código (provisional: lexical) | `retrieve_stub.py` |
| `grade` | código (umbrales calibrables) | `grade.py` |
| `judge_evidence` | modelo (`FakeProvider`, luego el real) | `providers.py` |
| `answer` | modelo | `providers.py` |
| `verify` | código — único lugar que puede rechazar una cita | `verify.py` |
| `risk` | código (tabla) — el modelo nunca baja el riesgo que fija la regla | `risk.py` |
| `human` | persona, vía `interrupt()` | `graph.py` |
| `ledger` | código, append-only | `ledger.py` |

## Cómo probarlo sin esperar al transformer

```bash
cd backend
python -m pytest tests/ -v              # 47 tests, todos contra data/corpus_v0 real
python scripts/demo_answer_graph.py      # corre 3 preguntas de ejemplo y muestra el grafo completo
```

El endpoint `POST /answer` (`api/app.py`) ya corre este grafo en vez de las respuestas guionadas de `mock.py`.
