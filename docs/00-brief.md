# 00 · El encargo (SOW del hack) y cómo lo cubre este diseño

Material recibido el 2026-10-17: `brief/sow.md` (declaración de trabajo sintética «Agente de Normativa y Políticas
Internas», cliente ficticio BCP, tarifa US$ 0, preparada para el hackathon) y `brief/sources.md` (fuentes públicas:
SBS, BCRP, UIF, MINJUS, BCBS, FATF, ISO, EU AI Act). Los originales `.docx` están al lado.

El SOW es el contrato de la demo: **lo que pide ahí es lo que se mide**. Esta página mapea cada exigencia al archivo
que la resuelve y al código que la implementa.

## Los 7 componentes del SOW → este repo

| Componente del SOW | Qué exige | Dónde está el diseño | Dónde va el código |
|---|---|---|---|
| 1. Corpus normativo y metadatos de vigencia | ≥ 25 documentos (SBS, Ley 26702, Basilea III, internos sintéticos) con número, publicación, vigencia, estado y relaciones modifica / deroga / sustituye; reporte de calidad de ingesta | `02-corpus.md`, `03-chunking.md`, `05-relations.md` (A) | `backend/regulabank/corpus/`, `backend/seeds/norms.csv` |
| 2. Recuperación con citación exacta | fragmento = artículo o numeral, con documento, versión, artículo **y página**; cita correcta ≥ 95 % del set | `03-chunking.md` (campos `page_start`/`page_end`), `07-embeddings.md`, `08-retrieval.md` | `backend/regulabank/search/` |
| 3. Agente con vigencia e historial | responde con la norma vigente, fecha de vigencia, cita exacta; resume qué cambió frente a versiones previas; declara cuando no hay sustento | `08-retrieval.md` (`validity`, `history`), `09-agents.md` (`answer_graph`), `charter/prompts/answer.md` | `backend/regulabank/agents/` |
| 4. Contradicciones y desactualización | entre versiones y entre documentos; clasifica `contradicción` / `desactualizado` / `referencia a norma derogada` / `vigencia futura`; muestra las dos citas | `05-relations.md` (C), `09-agents.md` (`conflict_graph`), `charter/prompts/conflict.md` | `backend/regulabank/graphs/bridge`, `/conflicts` |
| 5. Interfaz para analistas | caja de consulta, panel de fuentes con el fragmento original, indicador de vigencia, alertas de contradicción, botón de retroalimentación | `11-demo.md` | `frontend/` (Consulta, shelf, Conflictos; **falta el botón de retroalimentación**) |
| 6. Evaluación y trazabilidad | 40 preguntas con respuesta y fuente esperadas (incluye fuera de corpus y control sin contradicción); métricas automáticas; auditoría de cada consulta | `10-evaluation.md`, `charter/principles.md` (10) | `backend/regulabank/eval/`, `backend/seeds/questions.csv`, ledger |
| 7. Indicador de tiempo ahorrado | por consulta: minutos humanos de línea base por tipo vs. tiempo del agente; panel por consulta, área y acumulado | **nuevo**: abajo | `Trace.latency_ms` + `seeds/baseline_minutes.csv` + panel en `frontend/` |

## Ajustes al diseño que salen del SOW

1. **Clasificación de hallazgos con 4 clases, no 2.** `CONTRADICTS` y `STRICTER_THAN` se amplían a
   `contradiction` / `outdated` (política que cita una versión sustituida) / `repealed_reference` (cita una norma
   derogada) / `future_validity` (norma publicada con vigencia futura). Se actualiza `05-relations.md` (C) y el
   contrato `Conflict.relation`.
2. **Vigencia futura como estado de versión:** `valid_from > hoy` es una versión `scheduled`; la respuesta debe
   distinguir «rige hoy» de «regirá desde». Entra en `02-corpus.md` y en el contrato de `/answer` (`history`).
3. **Página en la cita.** El SOW exige página además de artículo: `page_start`/`page_end` ya están en el chunk;
   el formato de cita de `charter/style.md` pasa a `{norma | versión | art. | p. N | vigente desde}`.
4. **Resumen de cambios entre versiones.** No basta listar la historia: el nodo `answer` recibe el diff de texto
   entre la versión citada y la anterior (calculado por código) y lo resume en una oración con ambas citas.
5. **Tiempo ahorrado como dato.** Tabla `seeds/baseline_minutes.csv` (tipo de consulta → minutos humanos, validada
   con analistas) y `saved_minutes = baseline - latency` por consulta en el ledger; panel acumulado por área.
6. **Dos documentos vigentes que se contradicen (D-4):** el agente no elige; los muestra y recomienda escalar. Es
   `approve` en `charter/risk.md`.
7. **Corpus mínimo = 25 documentos.** La lista de `brief/sources.md` cubre los públicos (liquidez 9075-2012 y
   3296-2022, RFNE 4221-2023, clasificación y provisiones, riesgo de mercado, operacional, LA/FT, seguridad de la
   información, tercerización, medios de pago, Ley 26702, D. Leg. 1531, Ley 29733 y su reglamento, Basilea III);
   los internos sintéticos se escriben con los casos D-1 a D-6 sembrados.

## Los 6 casos sembrados (sección 4.3 del SOW)

Son el golden de contradicciones. Cada uno necesita dos documentos sintéticos en el corpus y una pregunta en
`seeds/questions.csv`.

| Caso | Documentos sintéticos | Hallazgo esperado | Clase |
|---|---|---|---|
| D-1 | Reglamento de Riesgo de Crédito v2019 (CPP a 60 días) y v2023 (30 días) | responde 30 citando v2023; informa que v2019 decía 60 | `history` |
| D-2 | Procedimiento de provisiones que cita Circular C-2018; C-2022 la deroga | procedimiento desactualizado; cita la norma que reemplazó | `repealed_reference` |
| D-3 | Política de Concentración (12 % del patrimonio efectivo) vs circular vigente (10 %) | contradicción con ambas citas | `contradiction` |
| D-4 | Manual de Tesorería (reporte diario) vs Procedimiento de Riesgo de Mercado (semanal), ambos vigentes | conflicto; no elige; escalar | `contradiction` + `approve` |
| D-5 | Circular publicada hoy, vigencia 2027-01-01 | distingue regla vigente hoy de la futura | `future_validity` |
| D-6 | Política de Capital 2020 con colchón de conservación menor que Basilea III y la circular vigente | política desactualizada; cita fuente vigente | `outdated` |

Criterio: detectar ≥ 5 de 6 con las dos citas, y ≤ 1 falso positivo en las preguntas de control.

## Las 7 consultas de demo (sección 4.5) y la línea base de tiempo

| Caso | Área | Consulta | Min humano → agente |
|---|---|---|---|
| U-1 | Riesgo de Crédito | ¿Desde cuántos días de atraso se reclasifica un crédito minorista a CPP? | 30 → 1 |
| U-2 | Provisiones | ¿Qué circular sustenta el cálculo de provisiones del procedimiento interno? | 35 → 2 |
| U-3 | Concentración | ¿Cuál es el límite de exposición a un solo deudor? | 45 → 2 |
| U-4 | Tesorería | ¿Con qué frecuencia se reporta la posición de liquidez? | 30 → 2 |
| U-5 | Cumplimiento | ¿Qué requisito de reporte aplica hoy y cuál desde el 1 de enero de 2027? | 25 → 1 |
| U-6 | Capital | ¿Qué colchón de conservación de capital debemos usar? | 40 → 2 |
| U-7 | Cumplimiento (fuera del corpus) | ¿Qué establece la normativa sobre criptoactivos en banca? | 20 → 1 |

Total: 225 → 11 minutos (95 %). Estos minutos son la primera versión de `seeds/baseline_minutes.csv`, marcados
`source = sow_assumption` hasta validarlos con un analista.

## Criterios de éxito (sección 4.4) → métricas de `10-evaluation.md`

| SOW | Meta | Métrica nuestra |
|---|---|---|
| cita exacta con documento, versión, artículo y página | 100 % | fracción de claims con `verify` ok y campos de cita completos |
| estado de vigencia con fecha en toda respuesta | 100 % | `validity` correcta |
| menciona versión anterior y resume el cambio | ≥ 90 % de las normas con versiones | nueva: `history_mentioned` por pregunta |
| contradicciones | ≥ 5/6 sembradas, ≤ 1 falso positivo | precisión y recall de la cascada sobre D-1..D-6 y controles |
| exactitud validada por analista | ≥ 85 % | rúbrica humana sobre las 40 |
| sin invención fuera del corpus | 100 % | abstención en negativas |
| tiempo ahorrado | ≥ 70 % por caso | `saved_minutes / baseline` |
| trazabilidad | 100 % | toda consulta en el ledger con fuentes y versión del modelo |

## Fuera de alcance (sección 14), para no construir de más

Sin integración con sistemas del banco, sin fine-tuning, sin actualización automática del corpus, sin opiniones
legales, sin documentos internos reales. El agente apoya; no dictamina.
