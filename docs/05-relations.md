# 05 · Relaciones: entre normas, entre artículos, entre política y norma

Tres familias, con extractor y verificación distintos. Ninguna arista entra sin `source` (de qué chunk salió),
`method` (regex / nli / judge / human) y `score`.

## A. Relaciones normativas (estructura y vigencia) → `horizon`

Formulaicas en el texto legal; se extraen con **regex + gramática chica**, se verifican literal y no pasan por modelo.

| Arista | Patrón de texto (ejemplos) | De → a |
|---|---|---|
| `MODIFIES` | «Modifíquese el artículo 12 de la Resolución SBS N.° X», «Sustitúyase el texto del numeral 3.1 …» | `Norm` → `Article` (y crea `Version`) |
| `REPLACES` | «Sustitúyase el artículo…», «el nuevo texto del artículo … es el siguiente» | `Version` → `Version` |
| `REPEALS` | «Deróguese…», «Déjese sin efecto…», «quedan derogadas las disposiciones que se opongan» (genérica: se marca `scope=generic`) | `Norm` → `Article` o `Norm` |
| `ADDS` | «Incorpórese el artículo 12-A…» | `Norm` → `Article` |
| `IMPLEMENTS` | «Reglamento de la Ley N.° …», «en uso de las atribuciones conferidas por el artículo 349 de la Ley General» | `Norm` → `Norm`/`Article` |
| `REFERS_TO` | «conforme al artículo 8», «de acuerdo con lo dispuesto en la Resolución SBS N.° …» | `Chunk` → `Article` |
| `DEFINES` | artículos de definiciones: «Para efectos de la presente norma se entiende por X: …» | `Version` → `Lens(defined_term)` |
| `ISSUED_BY` | cabecera | `Norm` → `Issuer` |
| `REGULATES` | tema asignado por clasificador o seed | `Norm` → `Topic` |
| `EFFECTIVE` | «entra en vigencia el … / al día siguiente de su publicación» | propiedad `valid_from` |

Verificación: la referencia resuelta debe existir en el catálogo de normas (si no, `unresolved` y se lista para
cargar la norma faltante). Un `MODIFIES` sin texto de reemplazo detectable produce la versión con `text=null` y
`review=true`; nunca se inventa el texto.

## B. Relaciones entre chunks → `focus`

Decisión 2026-10-17: DISRPT y ARI quedan fuera (demasiado que validar; las normas obligan, no argumentan). Entre
chunks solo hay estructura, referencias por regex, entidad compartida y similitud por embedding.

| Arista | Cómo | Para qué |
|---|---|---|
| `NEXT` | orden dentro del artículo y entre artículos consecutivos | contexto y PageRank |
| `PARENT` | jerarquía título/capítulo/artículo/numeral | mostrar ruta y agrupar |
| `REFERS_TO` | de A (regex) | multi salto («conforme al artículo 8») |
| `SIMILAR` | kNN por embedding (k=10) entre normas distintas, con `score` | rescate semántico en PageRank, pares candidatos para C |
| `SHARES_TERM` | mismo `defined_term` o misma entidad rara (df bajo) | puente temático explicable |

## C. Política interna ↔ norma (contradicción y cumplimiento) → `bridge`

Es la relación que vende el proyecto («interpretaciones inconsistentes»). Se construye en cascada, de lo gratis a
lo caro, y la decisión final es de una persona.

```
1. candidatos   pares (policy_chunk, norm_chunk) por híbrido: coseno (gemma) + léxico (TF-IDF) + entidad compartida
                (IDF alto: mismo plazo, mismo producto, misma definición); señales a percentil y combinadas con pesos
                declarados en seeds/params.toml; K pares por chunk de política, nunca dentro de la misma norma
2. nli          joeddav/xlm-roberta-large-xnli (RoBERTa large NLI con español) sobre (premise=norm, hypothesis=policy)
                → entailment / neutral / contradiction con score; también sobre numerales alineados (plazo vs plazo)
3. rules        comparación estructurada cuando ambas tienen valor: plazo_policy > plazo_norm → contradiction
                (determinista y explicable: «la política da 20 días; la norma exige 15»)
4. judge        Claude con salida estructurada {relation: complies|contradicts|stricter|unrelated, evidence:[quotes],
                reason} solo sobre el residuo (nli contradiction o rules disagree o score alto sin veredicto)
5. verify       código: las citas del juez existen literal en ambos chunks; los números citados están en el texto
6. human        interrupt: una persona confirma `CONTRADICTS` antes de que se muestre como hallazgo
```

Aristas resultantes:

```
(:Chunk{policy})-[:IMPLEMENTS {method, score}]->(:Article)
(:Chunk{policy})-[:CONTRADICTS {method, score, reason, evidence, reviewed_by, reviewed_at}]->(:Version)
(:Chunk{policy})-[:STRICTER_THAN {…}]->(:Version)     // la política es más exigente: no es contradicción
```

Lecciones de otros dominios que aplican aquí: los pares solo por embedding son «medio falsos» (se parecen en tono,
no en referente), por eso el híbrido con entidad compartida; un clasificador de relación fuera de dominio
(entrenado en debate) dio 27 «ataca» en 601 mil pares: **medir en 50 pares etiquetados antes de confiar en el NLI**.

## Impacto de una norma nueva (`impact`)

Al cargar una norma modificatoria: `MODIFIES` → artículos tocados → `IMPLEMENTS` inversas → chunks de políticas
afectadas → cola de revisión con la versión vieja y la nueva lado a lado. Es una consulta de grafo, no de modelo.

## Medición

- 50 pares política ↔ norma etiquetados a mano (complies / contradicts / stricter / unrelated), 10 contradicciones
  sembradas en las políticas sintéticas: precisión y recall de cada etapa de la cascada y del conjunto.
- Precisión del parser de A sobre 10 normas modificatorias reales: cada `MODIFIES` comparado con el texto
  consolidado oficial.
