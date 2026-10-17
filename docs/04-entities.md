# 04 · Entidades: el grafo `lens`

Entidades por chunk. Sirven para tres cosas: anclar la pregunta («plazo», «UIF», «deudor minorista»), sembrar el
PageRank y explicar la respuesta. No se usan como filtro duro: son señal.

## Etiquetas (dato en `seeds/entity_types.csv`, con motivo por fila)

| `entity_type` | Ejemplo en texto | Cómo se extrae | Valor estructurado |
|---|---|---|---|
| `norm_ref` | «Resolución SBS N.° 11356-2008», «Ley N.° 26702» | **regex** (formulaico) | `norm_id` resuelto |
| `article_ref` | «artículo 12°», «numeral 3.2 del artículo 8» | **regex** | `article_id` resuelto si se sabe la norma; si no, `local` |
| `deadline` | «dentro de los quince (15) días hábiles» | regex + GLiNER2 | `{n: 15, unit: business_day}` |
| `amount` | «S/ 10 000», «USD 10,000», «10 000 soles» | regex | `{value, currency}` |
| `percentage` | «1 % de la cartera», «ocho por ciento» | regex | `{value}` |
| `defined_term` | «Deudor minorista», «Operación sospechosa» | regex sobre artículos de definiciones + GLiNER2 | clave normalizada |
| `regulator` | SBS, BCRP, UIF-Perú, SMV, INDECOPI | gazetteer (seed) | `qid` opcional |
| `institution_type` | «empresa del sistema financiero», «caja municipal», «EDPYME» | gazetteer + GLiNER2 | clave |
| `role` | «Oficial de Cumplimiento», «Directorio», «Gerencia General», «Auditoría Interna» | GLiNER2 | clave |
| `product` | crédito hipotecario, tarjeta de crédito, depósito a plazo | GLiNER2 + gazetteer | clave |
| `risk` | riesgo de crédito, operacional, LAFT, ciberseguridad | gazetteer | clave |
| `obligation` | «deberá remitir», «está prohibido» | regla léxica (modal + verbo) | `{modality: must/must_not/may}` |
| `sanction` | multa, amonestación, intervención | GLiNER2 | clave |
| `report` | «Anexo N.° 6», «Reporte de Operaciones Sospechosas (ROS)» | regex + GLiNER2 | clave |

Regla de oro: **lo que tiene forma fija se extrae con regex y se verifica literal; el modelo solo para lo abierto**
(roles, productos, términos). Un número que no salió de una regex nunca entra a una respuesta.

## Modelos

| Papel | Modelo | Notas |
|---|---|---|
| NER abierto, etiquetas propias | `fastino/gliner2-large-v1` (GLiNER2) | zero-shot con las etiquetas de arriba en español; umbral bajo (0,3) al extraer, se guarda el score y se corta después |
| NER clásico (voto) | `MMG/xlm-roberta-large-ner-spanish`, `mrm8488/bert-spanish-cased-finetuned-ner` | PER/ORG/LOC/MISC; corroboran `regulator`, `role`, `institution_type`; `model_max_length=512` explícito |
| Segmentación | SaT `sat-3l-sm` + reglas | ventanas al presupuesto del modelo; nunca cortar dentro de «N.°» |

Todo corre en CPU/MPS para un corpus de demo (decenas de normas, pocos miles de chunks). GPU solo si pasa de
~50 mil chunks; entonces preflight con 2 chunks reales **más la fila más larga** (los chunks lista rompen por OOM).

## Filtro y voto (valores provisionales hasta calibrar)

- Entra una mención de GLiNER2 si `score >= 0,5` **o** tiene ≥ 2 votos de modelos clásicos con tramo solapado y tipo
  compatible. Los tipos regulatorios (`deadline`, `amount`, `norm_ref`) no necesitan voto: vienen de regex.
- Se descartan tramos que cruzan renglón, tipos propios en minúscula, y el mismo tramo con dos tipos de la misma
  familia (gana el de mayor score).
- Toda mención guarda `start`, `end`, `score`, `model`, `votes`; verificación literal `text[start:end] == mention`.

## Canonicalización

1. `norm()`: minúsculas, sin tildes (conserva la ñ), sin puntuación en bordes, sin artículos y tratamientos.
2. Siglas ↔ nombre completo dentro de la misma norma («Superintendencia de Banca, Seguros y AFP (SBS)» define el alias).
3. Plural → singular en términos, solo si el singular existe en el corpus.
4. Enlace a catálogo (`seeds/catalog.csv`: reguladores, tipos de institución, riesgos, productos) por nombre
   normalizado exacto o alias aceptado. Un nombre con varios candidatos no se adivina: queda sin enlace.
5. Mismo id de catálogo = un solo nodo `Lens`. **Compartir QID de Wikidata no fusiona** (medido en otro dominio:
   precisión 0,87 contra vara 0,97); solo propone alias a revisar.
6. **Curaduría por entidad, no por mención:** una entidad entra al grafo si aparece en ≥ 2 chunks (o 1 si es
   `defined_term`); un veredicto de juez por entidad (`ok | retype:<t> | generic | not_entity`) lo heredan todas sus
   menciones. En otro dominio esto subió la precisión de 51 % a 99 % con 34 lotes de juez.

## Nodos y aristas

```
(:Lens {id, type, name, key, catalog_id, n_chunks, n_norms})
(:Chunk)-[:MENTIONS {n, starts, ends, score}]->(:Lens)
(:Lens)-[:SAME_AS {source}]->(:Catalog)        // bridge
(:Lens {type: defined_term})-[:DEFINED_IN]->(:Version)   // dónde está la definición
```

## Medición

- 200 chunks etiquetados a mano (id explícito por etiqueta, nunca por posición): precisión y recall por tipo.
- Precisión mínima para que un tipo siembre el PageRank: 0,8 con intervalo de Wilson; por debajo, el tipo solo se
  muestra, no puntúa.
- Un muestreo estratificado tipo × franja de score va a `labels/mentions-todo.jsonl` para calibrar el corte.
