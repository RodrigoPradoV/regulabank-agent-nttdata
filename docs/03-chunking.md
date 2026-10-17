# 03 · Unidades: de la norma al chunk

## Jerarquía normativa (estructura del texto)

Las normas peruanas (leyes, resoluciones SBS, circulares) y las políticas internas comparten una estructura
numerada. Se parsea por reglas, no por modelo: los encabezados son formulaicos.

```
norm
└── title            «TÍTULO I», «TÍTULO PRELIMINAR»
    └── chapter      «CAPÍTULO II», «SUBCAPÍTULO»
        └── article  «Artículo 12.-», «Artículo 12°.-», «Artículo 12º»
            └── paragraph / numeral   «12.1», «1.», párrafos sin número
                └── literal           «a)», «b)», «i.»
└── provisions       «DISPOSICIONES FINALES», «TRANSITORIAS», «COMPLEMENTARIAS», «DEROGATORIAS»
└── annexes          «ANEXO N° 1»
```

Políticas internas: `policy → section (1., 1.1, 1.1.1) → clause`. Se mapea a la misma jerarquía: `section` juega
de `article`.

## Unidad de recuperación: el chunk

- **Unidad base = artículo** (o sección de política). Es la unidad que una persona cita y la que se modifica como
  bloque. Un artículo corto es un chunk; uno largo se parte por numerales.
- **Tope de largo relativo al corpus, no fijo:** percentil 95 del largo de artículos, medido sobre el corpus
  cargado. Un artículo más largo se parte en `ceil(len / cap)` piezas parejas, cortando en fin de numeral o fin de
  oración más cercano al objetivo; ninguna pieza baja de 0,5 × objetivo.
- **Sin solape y sin reescritura.** Cada chunk es un rango `[start, end)` de caracteres sobre el texto del artículo
  tal como quedó en la versión; los rangos cubren el artículo sin huecos. Así la cita literal se verifica con un
  `in` y se puede resaltar en el original.
- **Encabezado de contexto al embeber, no al citar:** el texto que se embebe lleva antepuesto
  `«{norm_short}, art. {article_no}{, numeral}. »` para que el vector sepa de qué norma es. El texto citado es el
  original sin encabezado.
- **Id estable por contenido:** `chunk_id = "c_" + sha1(f"{version_id}:{start}:{end}")[:16]`. Cambiar el texto de
  una versión produce otra versión y otros ids; los viejos no se borran.

## Campos de procedencia (obligatorios en cada chunk)

| Campo | Ejemplo | Para qué |
|---|---|---|
| `chunk_id` | `c_3f9a…` | clave |
| `norm_id` | `pe-sbs-res-11356-2008` | agrupar, mostrar |
| `norm_short` | `Res. SBS 11356-2008` | encabezado y cita |
| `norm_kind` | `law` / `sbs_resolution` / `sbs_circular` / `bcrp_circular` / `internal_policy` | jerarquía |
| `article_id` | `pe-sbs-res-11356-2008#art-12` | nodo del artículo (estable entre versiones) |
| `article_no` | `12` | cita |
| `path` | `TÍTULO II > CAPÍTULO I > Artículo 12 > 12.3` | mostrar contexto |
| `version_id` | `pe-sbs-res-11356-2008#art-12@v3` | versión del texto |
| `valid_from` / `valid_to` | `2019-04-01` / `null` | vigencia (`null` = vigente) |
| `start` / `end` | `0` / `1180` | rango sobre el texto de la versión |
| `chunk_index` / `n_chunks` | `1` / `2` | orden dentro del artículo |
| `prev_chunk_id` / `next_chunk_id` | | arista `NEXT` |
| `source_url` / `source_sha256` / `page_start` / `page_end` | | verificación y enlace al PDF |
| `citation` | `Res. SBS N.° 11356-2008, art. 12, num. 12.3 (texto vigente desde 2019-04-01)` | lo que ve la persona |

## Validación antes de escribir

Falla la construcción (no se escribe nada) si hay: ids duplicados, rangos que no reproducen el texto, huecos
entre chunks de un mismo artículo, `prev`/`next` inconsistentes, artículos sin `version_id` o versión sin
`valid_from`.

## Capa de oraciones (opcional, después del MVP)

Para citas cortas y hablables: segmentar cada chunk en oraciones con SaT (`sat-3l-sm`, ver `07-embeddings.md`)
más dos reglas (no cortar dentro de «N.°», no cortar numerales), `sentence_id = chunk_id:n`, offsets sobre el
chunk. Se usa para elegir la oración que mejor sostiene una afirmación y para resaltar.

## Medición propia de esta etapa

- Artículos detectados vs. artículos reales en 10 normas revisadas a mano (recall del parser ≥ 0,98).
- Distribución de largos; valor efectivo de `cap` registrado en el manifiesto de cada build.
- Fingerprint del conjunto de chunks (hash independiente del orden): un refactor no debe moverlo.
