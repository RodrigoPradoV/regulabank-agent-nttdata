# 01 · El problema

## Reto

Reto Banca, punto 2 del hack: «Normativa y políticas internas: encontrar la información correcta y vigente entre
múltiples documentos puede ser lento y generar interpretaciones inconsistentes».

Descompuesto:

| Dolor | Causa | Qué lo resuelve aquí |
|---|---|---|
| lento | la respuesta vive repartida en una ley, dos resoluciones, una circular y tres políticas internas que se remiten entre sí | grafo de referencias cruzadas + PageRank personalizado: multi salto en una consulta |
| no vigente | las normas se modifican por artículos sueltos; un PDF viejo sigue circulando | versiones con `valid_from`/`valid_to`, aristas `MODIFIES`/`REPEALS`, `as_of` en la pregunta |
| inconsistente | dos analistas leen distinto; la política interna contradice a la norma actualizada | respuesta siempre con cita literal; detección de contradicciones política ↔ norma como aristas revisadas por persona |
| no trazable | nadie sabe de dónde salió la respuesta | ledger por consulta: chunks vistos, citas verificadas, versión del prompt, costo, quién aprobó |

## Usuarios

- **Analista de cumplimiento / riesgos / legal:** pregunta en lenguaje natural, necesita el artículo exacto y su
  vigencia. Usuario principal de la demo.
- **Oficial de cumplimiento normativo:** necesita saber qué políticas internas quedaron desalineadas cuando sale
  una norma nueva (impacto de cambio).
- **Área de negocio (créditos, operaciones, canales):** pregunta «¿puedo hacer X?» y necesita un sí/no con base.
- **Auditoría interna / regulador:** necesita la traza completa de por qué se respondió así.

## Preguntas tipo (base del golden)

Se clasifican por **escenario**; cada escenario tiene su contrato de recuperación (ver `08-retrieval.md`).

| Escenario | Ejemplo | Qué exige |
|---|---|---|
| `lookup` | «¿Cuál es el plazo máximo para reportar una operación sospechosa a la UIF?» | un artículo, cita literal, vigencia |
| `definition` | «¿Qué se entiende por deudor minorista?» | término definido + norma que lo define |
| `threshold` | «¿Desde qué monto una operación en efectivo se registra obligatoriamente?» | número exacto sacado del texto, nunca del modelo |
| `procedure` | «¿Qué pasos sigue la clasificación de un deudor con atraso de 60 días?» | varios artículos encadenados en orden |
| `validity` | «¿Está vigente el artículo 12 de la Resolución X al 1 de enero de 2025?» | historia de versiones |
| `crossref` | «¿Qué norma reglamenta el artículo Y de la Ley 26702 en materia de provisiones?» | referencias cruzadas (multi salto) |
| `policy_vs_norm` | «¿Nuestra política de crédito respeta el límite de exposición del artículo Z?» | par política ↔ norma + juicio + persona |
| `impact` | «Salió la Resolución W: ¿qué políticas internas toca?» | aristas `IMPLEMENTS` desde políticas hacia los artículos modificados |
| `negative` | «¿Cuál es la tasa de interés máxima que fija la SBS para hipotecas?» (no la fija) | abstención con explicación |

Mínimo para el hack: 30 preguntas, al menos 3 por escenario, 5 negativas. Cada una con los `chunk_id` que la
responden. Ver `10-evaluation.md`.

## Criterio de éxito

| Métrica | Meta demo | Meta producto |
|---|---|---|
| recall@8 de chunks correctos | ≥ 0,80 | ≥ 0,90 |
| citas literales verificadas | 100 % de las afirmaciones | 100 % |
| abstención correcta en negativas | ≥ 4/5 | ≥ 0,95 |
| vigencia correcta en `validity` | 100 % | 100 % |
| contradicciones política ↔ norma detectadas en el set sembrado | ≥ 2/3 | medido contra auditoría |
| latencia de respuesta | < 10 s | < 5 s |
| costo por consulta | visible en el ledger | < 0,02 USD |

## Qué NO hacemos

- No damos opinión legal: el sistema cita y ordena; interpretar es de la persona.
- No ejecutamos acciones (no cambia políticas, no envía reportes): propone y una persona aprueba.
- No usamos datos de clientes ni cifras internas reales: corpus público más políticas internas **sintéticas**.
- No agentes que conversan entre sí: un workflow con dueños por nodo (código, modelo, juez o persona).
- No resumen global del corpus (estilo GraphRAG global con comunidades): caro y sin señal; preguntas locales con
  rescate por grafo.
