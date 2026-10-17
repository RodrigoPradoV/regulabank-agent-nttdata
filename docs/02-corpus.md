# 02 · Corpus: fuentes, captura, identidad, versiones y vigencia

## Fuentes (Perú, sector bancario)

Corpus público primero; políticas internas **sintéticas** para la demo (nunca documentos reales de un banco).

| Capa | Fuente | Ejemplos (verificar vigencia y número antes de cargar) | `norm_kind` |
|---|---|---|---|
| Ley | Congreso / El Peruano | Ley 26702 (Ley General del Sistema Financiero y Orgánica de la SBS); Ley 29571 (Código de Protección del Consumidor); Ley 29733 (Datos Personales); Ley 27693 (UIF) | `law` |
| Reglamento SBS | sbs.gob.pe/normativa | Res. SBS 11356-2008 (clasificación del deudor y provisiones); Res. SBS 3780-2011 (riesgo de crédito); Res. SBS 272-2017 (gobierno corporativo y gestión integral de riesgos); Res. SBS 504-2021 (seguridad de la información y ciberseguridad); Res. SBS 2660-2015 (riesgos de LAFT); Res. SBS 3274-2017 (conducta de mercado) | `sbs_resolution` |
| Circular SBS / BCRP | SBS, BCRP | circulares de encaje, reporte de operaciones, tasas de interés | `sbs_circular`, `bcrp_circular` |
| Estándar externo | BIS | Basilea III (referencia, no vinculante) | `standard` |
| Política interna | sintética | Política de Crédito, Manual de Prevención LAFT, Política de Seguridad de la Información, Procedimiento de Clasificación de Deudores | `internal_policy` |

Jerarquía (para resolver conflictos y para ordenar): `law > sbs_resolution > sbs_circular = bcrp_circular > internal_policy > procedure`. Es dato en `seeds/norm_kinds.csv`, no un enum en código.

Dónde buscar texto consolidado: el portal de normativa de la SBS publica «texto actualizado» de los reglamentos; el SPIJ (Sistema Peruano de Información Jurídica) tiene leyes consolidadas; El Peruano tiene cada modificación por fecha. Para la demo basta con 8 a 12 normas y 3 a 4 políticas sintéticas con contradicciones sembradas a propósito.

## Captura (patrón de ingesta por capas)

```
bronze   PDF/HTML original + sha256 + url + fecha de captura     (nunca se modifica)
silver   texto extraído por página con offsets; tabla captures/extractions con outcome y gate
gold     release versionado: norms, articles, versions, chunks (text == version_text[start:end])
views    índices derivados (LanceDB, grafos, Parquet) construidos desde un release fijo; nunca escriben en él
```

- **httpx para HTML y PDF; sin navegador.** Si una fuente exige navegador, se baja a mano para la demo y se anota.
- **Ritmo:** lote de prueba de 3 documentos; 5 a 10 s entre peticiones a portales del Estado; frenar al primer 403.
- **Extracción de PDF:** texto por página con offsets (`pymupdf`); si la página es imagen, OCR y marca `ocr=true`
  (las normas antiguas del Peruano suelen venir escaneadas). Texto OCR no se cita literal sin revisión.
- **Gate de captura** (si falla, `quarantine:<checks>` y no entra al gold): tiene título, tiene cuerpo, los
  anclajes resuelven (`text == stream[start:end]`), número de norma detectado, al menos un artículo parseado, fecha
  de publicación detectada.
- **Evidencia congelada:** el juez y los verificadores leen el bronze/silver por hash, nunca la web en vivo.

## Identidad de una norma y de un artículo

- `norm_id` = `pe-{issuer}-{kind}-{number}-{year}` (`pe-sbs-res-11356-2008`, `pe-congreso-ley-26702-1996`).
  Se deriva del encabezado por regex más la tabla `seeds/norms.csv` (número, título corto, emisor, fecha de
  publicación, url). Si el parser y la tabla discrepan, falla el build.
- `article_id` = `{norm_id}#art-{n}`; estable aunque el texto cambie. Los artículos con sufijo («12-A») se
  conservan como `art-12-A`.
- **Reconciliación entre capturas de la misma norma** (texto consolidado nuevo vs. anterior), por artículo:
  idéntico → misma versión; similitud ≥ 0,90 → versión nueva (`MODIFIED`); 0,70 a 0,90 → `review`;
  sin par → `new` o `retired`. Los umbrales son provisionales hasta medir con 30 pares etiquetados.

## Versiones y vigencia (lo que distingue este corpus)

Cada `article` tiene una lista de `version` con:

| Campo | Significado |
|---|---|
| `version_id` | `{article_id}@v{n}` |
| `text` | texto de esa versión |
| `valid_from` | fecha de entrada en vigencia (de la norma modificatoria o de la original) |
| `valid_to` | `null` si vigente; si no, el día anterior a la vigencia de la siguiente |
| `changed_by` | `norm_id` de la norma que la introdujo (`MODIFIES`, `REPLACES`, `REPEALS`) |
| `change_kind` | `original` / `modified` / `replaced` / `repealed` / `added` |
| `source_sha256`, `page_start`, `page_end` | evidencia |

Reglas:
- **Vigencia por defecto:** «entra en vigencia al día siguiente de su publicación» salvo cláusula expresa; la
  fecha de publicación se toma de la cabecera del Peruano o del portal, con `published_via` registrado.
- **Derogado no se borra:** la versión queda con `valid_to` y `change_kind=repealed`; se puede citar como historia.
- **`as_of` resuelve la versión:** `valid_from <= as_of < valid_to` (o `valid_to is null`). Con `as_of` en el
  pasado se responde con la versión de entonces y se avisa.
- **Las normas modificatorias se parsean como norma y como lista de operaciones:** «Modifíquese el artículo 12 de la
  Resolución SBS N.° X» produce una arista `MODIFIES` y una versión nueva en el artículo destino (ver
  `05-relations.md`).
- **Política interna:** `version` por fecha de aprobación; además `IMPLEMENTS` hacia los artículos que cumple.

## Manifiesto del release

`manifest.json`: id, fecha, lista de normas con sha256, conteos (norms, articles, versions, chunks), parámetros
efectivos (cap de chunk, umbrales de reconciliación), fingerprint del gold y versión del código. Un build sin
manifiesto no existe.
