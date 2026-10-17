# 11 · El hack: plan por sprint, demo e impacto

## Qué se entrega

Problema, solución, demo funcional, impacto y código. Jurado y mentores vienen de banca; lenguaje que entienden:
**confianza, trazabilidad, dueño auditable, vigencia, cumplimiento**.

## Plan (3 sprints, equipo de 4)

Un constructor por pieza, lecturas en paralelo, integración de a uno. Todo se construye con `MODEL_PROVIDER=mock`
hasta el sprint 3.

| Sprint | Pieza | Dueño | Hecho cuando |
|---|---|---|---|
| 1 · Build | corpus mínimo: 8-12 normas públicas + 3 políticas sintéticas con 10 contradicciones sembradas; parser de artículos; chunks con procedencia; `seeds/norms.csv` | A | `manifest.json` con conteos; 20 chunks abiertos a mano |
| 1 · Build | LanceDB (gemma + FTS) + retrieval denso + RRF + `verify` de citas | B | 30 preguntas golden con recall@8 medido contra denso solo |
| 1 · Build | `horizon` (versiones, `MODIFIES`/`REPEALS`/`REFERS_TO` por regex) + PageRank en memoria | C | `validity` y `crossref` responden; nDCG vs denso solo |
| 1 · Build | `answer_graph` con `FakeProvider`: `read → retrieve → answer → verify`, `draw_mermaid()` | D | `invoke` cierra; diagrama en README |
| 2 · Agentic | `grade` + `judge_evidence` + `MAX_FIXES` + tabla de riesgo + `interrupt` + `SqliteSaver` | D + B | un caso bueno, uno rechazado por `verify`, uno que espera a la persona |
| 2 · Agentic | `conflict_graph`: pares híbridos → NLI → rules → juez (mock) → HITL | C + A | las 10 contradicciones sembradas: cuántas encuentra cada etapa |
| 2 · Agentic | UI mínima (Streamlit o React): pregunta, `as_of`, respuesta con citas, historia del artículo, cola de aprobación, ledger | A | demo navegable |
| 3 · Real | proveedor real (Anthropic o Azure OpenAI), una llamada de prueba leyendo `usage`, ledger con costo; tests de funciones; README con «status & honesty» | todos | demo en vivo + números |

## Guion de la demo (6 minutos)

1. **El problema en una pantalla:** la misma pregunta («¿plazo para reportar una operación sospechosa?») a dos
   PDFs: uno viejo y uno vigente. Respuestas distintas.
2. **Respuesta con cita y vigencia:** la pregunta en la UI; respuesta con `«cita» {norma | art. | vigente desde}`;
   clic en la cita abre el PDF en la página.
3. **Multi salto:** `crossref`: «¿qué reglamenta el artículo X de la Ley?» → el grafo trae el reglamento aunque el
   embedding no lo vea. Mostrar el camino `REFERS_TO`.
4. **El tiempo:** misma pregunta con `as_of` 2018 y 2025: versiones distintas, con la norma modificatoria.
5. **El modelo inventa y el verificador lo para:** forzar una cita alterada (mock); `verify` devuelve
   `quote_altered`; segundo intento; respuesta limpia. Costo de la corrida en el ledger.
6. **Contradicción política ↔ norma:** la política sintética da 20 días, la norma exige 15; `rules` lo detecta,
   el juez lo confirma, queda en cola; una persona aprueba; aparece como hallazgo con ambas citas.
7. **Cerrar y reanudar:** matar el proceso con un caso en `pending_human`; levantar; `Command(resume=…)` sigue.
8. **Números:** recall@8 vs denso solo, citas verificadas 100 %, abstención en negativas, costo por consulta.

## Impacto (cómo contarlo)

- Tiempo del analista: de buscar en N documentos a una consulta con cita y vigencia.
- Consistencia: la misma pregunta → la misma cita (pass^3).
- Riesgo regulatorio: contradicciones política ↔ norma detectadas antes de la auditoría; impacto de una norma nueva
  en minutos.
- Auditoría: ledger por consulta con evidencia, versión y quién aprobó.
- Honestidad: lo que no se midió se dice; silver ≠ golden; el juez LLM no se mide con sus propias etiquetas.

## Estructura del repo

```
backend/
  regulabank/
    corpus/      capture, parse, chunks, versions, release        (02, 03)
    graphs/      horizon, lens, focus, bridge, load, ppr          (04, 05, 06)
    search/      embed, index, retrieve, rank, verify, quotes     (07, 08)
    agents/      answer_graph, conflict_graph, onboard_graph, tools, providers, budget, ledger  (09)
    eval/        golden, metrics, judge, fingerprint              (10)
    api/         FastAPI: /norms, /articles, /answer, /conflicts, /ledger
    shared/      config, stores, contracts
  seeds/         norms.csv, norm_kinds.csv, entity_types.csv, catalog.csv, risk_rules.csv, questions.csv, params.toml
  scripts/       smoke.py, golden_retrieval.py
  tests/         funciones sin grafo; grafo con juez falso; golden de regresión
frontend/        Angular (sidebar, topbar, shelf; Textos, Conflictos, Consulta)
charter/         comportamiento de los LLMs: principios, prompts versionados, herramientas, riesgo
infra/           compose.yaml, Dockerfile
docs/            estos archivos
data/            (gitignored) bronze/ silver/ releases/ views/ state/
```

Modo mock sin claves, diagrama del grafo, tabla «quién decide en cada nodo» y benchmark contra baseline en el
README: es lo que tienen los repos que ganaron ediciones anteriores.
