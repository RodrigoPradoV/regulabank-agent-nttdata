# 10 · Medición

«Lo que no se mide no se gestiona.» Golden desde el día uno; cada cambio entra solo si mejora en el golden
reservado sin empeorar otro escenario.

## Golden de recuperación

- `seeds/questions.csv`: `question_id, text, scenario, as_of, expected_chunk_ids (idx:valor, explícitos, nunca por
  posición), expected_abstain, reserved, author, date`.
- Mínimo demo: 30 preguntas (3+ por escenario, 5 negativas). Producto: ~150, generadas desde chunks al azar y
  verificadas por una persona; **un tercio reservado** que nunca entra a prompts, ejemplos ni calibración.
- Para `validity`: preguntas con `as_of` en tres fechas (antes, entre y después de una modificación).
- Para `policy_vs_norm`: 10 contradicciones sembradas en las políticas sintéticas con su par esperado.

## Métricas

| Qué | Métrica | Cómo |
|---|---|---|
| recuperación | recall@5, recall@10, MRR, nDCG@8 por escenario | contra `expected_chunk_ids` |
| juicio de relevancia (pooling) | UMBRELA 0-3 con LLM, dos pasadas en orden distinto, acuerdo sí/no reportado | top-10 de cada variante; juicios en `judgments.jsonl`, no se repiten |
| citas | fracción de afirmaciones con cita literal verificada (meta 1,0) | `verify` |
| vigencia | exactitud de la versión elegida en `validity` (meta 1,0) | código |
| abstención | precisión y recall sobre negativas | código |
| contradicciones | precisión y recall de cada etapa de la cascada (nli, rules, judge) y del conjunto | 50 pares etiquetados |
| fiabilidad | pass^k (k=3): la misma pregunta responde igual tres veces | corrida repetida |
| respuesta | rúbrica 0-2 con LLM: respaldo, fidelidad, abstención; A/B pareado para cambios de redacción | `answer_eval --pair` |
| costo y latencia | USD y ms por consulta, p50/p95 | ledger |
| baseline obligatorio | **denso solo** (sin grafo, sin reranker) | toda mejora se compara contra esto |

Con 30 preguntas una diferencia de 0,01 de nDCG no es separable: reportar intervalo (bootstrap) y no fijar nada
por debajo del ruido. El juez LLM varía ±0,2 entre corridas idénticas: dos pasadas.

## Regresión y huellas

- **Golden de regresión:** `scripts/golden_retrieval.py --write|--check` congela los `chunk_id` del top-8 de cada
  pregunta; el test falla si cambian y se regenera solo a propósito.
- **Fingerprint** del gold (hash por fila, ordenados y vueltos a hashear, sin columnas volátiles): un refactor no
  debe moverla. Cambiar el parser o el cap de chunk la mueve y eso se declara en el ledger.
- **Huella de cada vista** (`provenance`: fingerprint del release, hash de parámetros, versión de código, modelo):
  cambiar cualquiera invalida la vista.
- **Determinismo:** correr el build con `PYTHONHASHSEED` 2, 3 y 7; desempates por `set` y sumas de float ya
  rompieron un golden en otro proyecto.

## Calidad del código

- `grade` por módulo: cobertura 40, complejidad 20, errores tragados 10, acoplamiento 10, efectos cubiertos 10,
  docstrings 10. `solid ≥ 75`, `fair 55-75`, `brittle < 55`. Compuerta: ≥ 75 en lo tocado.
- Test de capas: `corpus → graphs → search → agents → api`; nadie importa hacia arriba.
- Después de cualquier limpieza, medir de punta a punta, no solo correr tests: dos regresiones en otro proyecto las
  atrapó la medición, no la suite.

## Autonomía (para el producto, no para la demo)

Tres números de logs y estado, contra la misión «responder correcto y vigente, escalar lo riesgoso»: cobertura
(preguntas respondidas con cita / total), días sin intervención, auto reparación (incidentes resueltos solos /
total). Un escenario corre sin revisión humana solo si el límite inferior del intervalo de su precisión supera el
umbral fijado por quien lleva el proyecto.
