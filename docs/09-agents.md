# 09 · Agentes: LangGraph, juez, verificador, triage de riesgo y humano en el bucle

LangGraph orquesta; no decide. Cada nodo es una función normal, testeable sin grafo. El modelo entra en dos nodos
(`judge` y `answer`) con herramientas de solo lectura sobre evidencia congelada y salida estructurada. Todo lo que
puede ser regla es regla.

## Cuándo hace falta grafo

Hay grafo porque hay: ramas (`route` por escenario y por calidad de la evidencia), una vuelta con tope
(`answer → verify → answer`, `MAX_FIXES = 2`), pausa humana (`interrupt`), checkpointer (`SqliteSaver`, un
`thread_id` por consulta) y abanico (`Send` por par política ↔ norma en el grafo de contradicciones). Sin eso
sería una función.

## Grafo 1: `answer_graph` (consulta del analista)

```
START → read → retrieve → grade ─┬─ no_evidence ──────────────→ abstain → ledger → END
                                 ├─ ambiguous → judge_evidence ─┬─ confirm → answer
                                 │                              └─ reject  → abstain
                                 └─ ok ─────────────────────────→ answer
answer → verify ─┬─ ok ──────→ risk ─┬─ auto    → deliver → ledger → END
                 │                   ├─ notify  → deliver(+flag) → ledger → END
                 │                   └─ approve → [interrupt] → human ─┬─ accept → deliver → ledger → END
                 │                                                     ├─ edit   → verify (otra vez)
                 │                                                     └─ reject → archive → ledger → END
                 └─ fail (fixes < 2) → answer (con el error a la vista)
                 └─ fail (fixes = 2) → rejected → ledger → END
```

| Nodo | Quién decide | Qué hace |
|---|---|---|
| `read` | código | escenario, normas, `as_of` (`08-retrieval.md`) |
| `retrieve` | código + embedding | los 8 `Hit` con traza; llena `seen` |
| `grade` | código | `ok` / `ambiguous` / `no_evidence` por `evidence.mean6` y `rescue_floor` (estilo CRAG, con umbrales calibrados, no con prompt) |
| `judge_evidence` | modelo | sobre los 4 mejores: `{relevant: [chunk_id], reason}`; solo ids de `seen` |
| `answer` | modelo | `Answer{claims: [Claim{text, chunk_id, quote}], as_of, abstain: bool, risk_hint}`; una afirmación = una cita |
| `verify` | código | `quote in text`, `chunk_id in seen`, vigencia de cada cita a `as_of`, números de `text` presentes en `quote`, ninguna norma citada fuera de `seen`; devuelve faltas tipadas: `quote_missing`, `quote_altered`, `foreign_fact`, `not_seen`, `not_in_force`, `fake_consistency` (dice que la política cumple sin arista) |
| `risk` | código (tabla) | `auto` / `notify` / `approve` según reglas: escenario `policy_vs_norm` o `impact` → `approve`; `threshold` con número → `notify`; cita a versión no vigente con `as_of` hoy → `approve`; resto `auto`. Si el modelo sugiere menos riesgo que la regla, gana la regla |
| `human` | persona | `interrupt(HumanInterrupt{action_request, config{allow_accept, allow_edit, allow_respond, allow_ignore}, description})` → `HumanResponse{type, args}`; se reanuda con `Command(resume=…)` |
| `deliver` | código | respuesta final con citas en formato fijo; la redacción natural solo si pasa `verify`; si falla dos veces, plantilla |
| `ledger` | código | una línea por consulta: `thread_id, scenario, seen, claims, verify_result, risk, human_decision, model, prompt_version, tokens_in/out, cost_usd, latency_ms` |

Estado (chico, con referencias, no textos enteros):

```python
class State(TypedDict, total=False):
    question: str; as_of: str; scenario: str
    hits: list[Hit]; seen: list[str]
    grade: Literal["ok","ambiguous","no_evidence"]
    answer: Answer | None; faults: list[Fault]; fixes: int
    risk: Literal["auto","notify","approve"]; human: HumanResponse | None
    cost_usd: float; status: Literal["ok","abstained","rejected","pending_human","quota_deferred"]
```

## Grafo 2: `conflict_graph` (política ↔ norma, offline, por lotes)

```
START → select_pairs → [Send por par] → nli → rules → route ─┬─ clear → store
                                                            └─ residue → budget → judge → verify → route2 ─┬─ contradicts → [interrupt] human → store
                                                                                                          └─ else → store
```

- Un `thread_id` por par; idempotente por `(policy_chunk_id, norm_version_id, prompt_version)`.
- `budget` comprueba el tope **antes** de llamar; al tope, el par queda `quota_deferred` y la corrida termina limpia.
- Las transiciones (`pending → queued → in_review → resolved | rejected | quota_deferred`) se escriben en SQLite con
  caso, de, a, cuándo, por qué y corrida. El checkpointer solo sirve para retomar.

## Grafo 3: `onboard_graph` (cargar una norma nueva)

```
capture → parse → relations_A → diff_versions → impact → [interrupt] human approves the diff → publish release → rebuild views
```

La persona aprueba un diff con números (artículos nuevos, modificados, políticas afectadas), no un texto.

## Reglas del nodo del modelo

- Proveedor abstraído: `MODEL_PROVIDER=mock|anthropic|azure_openai`. Todo el flujo se construye y se prueba con el
  `FakeProvider` guionado; el real entra al final.
- Salida validada con Pydantic; reintento con el error a la vista; a la tercera `rejected`. Nunca rellenar con
  valores por defecto: sería un veredicto inventado.
- Herramientas del juez, declaradas una vez con esquema (nombre en inglés): `read_chunk(chunk_id)`,
  `neighbors(chunk_id)`, `article_history(article_id)`, `refers_to(chunk_id)`, `policy_links(chunk_id)`. Todas de
  solo lectura sobre el release congelado; el error vuelve como dato, no como excepción.
- Leer `usage` y `finish_reason`; si `length`, parar la corrida. `max_tokens` dimensionado al esquema.
- Caché por contenido (sha de modelo + mensajes + prompt_version) antes de llamar.
- Límite de cupo = `quota_deferred`, no error: esperar a la hora de reinicio más 120 s.
- Cada decisión guarda versión del grafo, del prompt y del modelo, para invalidar en bloque.

## Humano en el bucle

- La pausa es **propiedad del tipo de caso, declarada como dato** (`seeds/risk_rules.csv`: escenario, condición,
  nivel). El grafo la cumple con `interrupt`; no se decide en el prompt.
- Cola con SLA: lo pendiente se lista con evidencia lista para revisar; el resto sigue corriendo.
- La decisión humana se guarda como dato (`human_decision`) y sirve para recalibrar umbrales (`risk`, `mean6`),
  nunca para reentrenar en caliente.
- Un juez no se evalúa contra etiquetas hechas por el mismo modelo: lo que etiqueta Claude es *silver*; el golden
  lo revisa una persona.

## Pruebas

- Nodos como funciones; grafo con juez falso (veredictos fijos de fixture). La suite no llama al modelo.
- `draw_mermaid()` genera el diagrama para el README; no se dibuja a mano.
- Tabla «quién decide en cada nodo» (arriba) va en el README del repo.
