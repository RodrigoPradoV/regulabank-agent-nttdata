Agente

# 1. Partes

Esta declaración de trabajo (“SOW”) se establece entre:

<span class="mark">Consultor:</span> FluentData, SAC

Cliente: Banco de Crédito del Perú (BCP) – cliente ficticio para fines de hackathon

Esta SOW se rige y se incorpora al Acuerdo Maestro de Servicios (“MSA”) entre las partes, si aplica. En caso de conflicto, esta SOW rige con respecto a los servicios aquí descritos.

# 2. Resumen Ejecutivo

El Cliente busca contratar al Consultor para diseñar y construir un agente de IA, agnóstico de proveedor de nube y de modelo de lenguaje, basado en recuperación aumentada por generación (RAG) que responda las consultas normativas de los analistas de riesgo citando la fuente exacta (documento, versión, artículo y página), indicando el estado de vigencia de cada norma citada, resumiendo sus actualizaciones respecto de versiones anteriores y señalando contradicciones entre documentos o documentos desactualizados. La solución responde a las áreas de Riesgos (crédito, mercado, liquidez y operacional) y Cumplimiento Normativo, e incorpora un indicador del tiempo que ahorra a un analista frente a hacer la misma consulta de forma manual.

El Consultor entregará los Servicios con una tarifa fija, facturada como un único monto fijo, según lo establecido en esta SOW. Por tratarse de un documento sintético preparado para una hackathon, la tarifa de esta SOW es de US\$ 0.00.

Esta SOW define el alcance de los servicios, los entregables, los criterios de aceptación y los términos comerciales que rigen el compromiso.

# 3. Contexto Comercial, Declaración del Problema y Solución Propuesta

## 3.1 Contexto Comercial

El BCP opera en un entorno donde las políticas de riesgo, las circulares y resoluciones de la Superintendencia de Banca, Seguros y AFP (SBS), los lineamientos de Basilea III y los procedimientos internos se encuentran dispersos en distintos documentos, versiones y áreas (Riesgos, Cumplimiento Normativo, Tesorería y Operaciones). Cuando un analista tiene una duda normativa, hoy la resuelve preguntando a un colega o revisando PDFs extensos, sin una vista única de qué norma está vigente, qué la modificó y qué documentos internos aún la citan.

## 3.2 Declaración del Problema

El Cliente ha identificado los siguientes desafíos principales que impulsan esta iniciativa:

- **Búsqueda lenta en documentos dispersos:** la información vive en PDFs largos de distintas áreas, por lo que ubicar la cláusula aplicable consume tiempo del analista que debería dedicar a evaluar riesgo.

- **Vigencia incierta:** coexisten versiones de una misma circular o reglamento y no hay una fuente única que indique cuál es la vigente ni desde qué fecha, lo que lleva a citar normas modificadas o derogadas.

- **Interpretación inconsistente:** distintos analistas llegan a respuestas diferentes sobre la misma norma, porque dependen de qué colega consultan o de qué versión del documento tienen a mano.

- **Contradicciones sin detectar:** las políticas y procedimientos internos pueden contradecir la normativa vigente, o a otro documento interno, sin que nadie lo advierta hasta una revisión o una observación del regulador.

Estos desafíos resultan en:

- Riesgo regulatorio y operativo: decisiones tomadas con una norma desactualizada o con una interpretación distinta entre áreas pueden derivar en incumplimientos u observaciones del regulador.

- Pérdida de productividad: cada consulta normativa interrumpe a un colega y retrasa el análisis de riesgo real, y el conocimiento sobre qué norma aplica queda en las personas y no en un sistema.

## 3.3 Descripción General de la Solución Propuesta

El Consultor proporcionará servicios profesionales diseñados para abordar estos desafíos mediante la entrega de los productos de trabajo descritos en esta SOW.

Los Servicios y entregables definidos aquí representan un alcance de trabajo definido. Cualquier cambio material en el alcance, las suposiciones o los entregables requiere una orden de cambio por escrito o una SOW enmendada ejecutada por ambas partes.

- Indexar el corpus normativo con metadatos de vigencia, versión y relaciones entre normas (modifica, deroga, sustituye), de modo que cada consulta se responda solo con la fuente aplicable.

- Responder cada consulta con la cita exacta, el estado de vigencia, el historial de versiones anteriores y la advertencia explícita cuando no existe sustento en el corpus.

- Comparar versiones y documentos para señalar contradicciones y desactualizaciones, mostrando las dos citas en conflicto para que el analista decida.

# 4. Alcance de los Servicios y Entregables

## 4.1 Servicios Incluidos en el Alcance

- **Componente 1 – Corpus normativo y metadatos de vigencia:** ingesta de un corpus mínimo de 25 documentos, compuesto por normativa pública de la SBS (resoluciones, circulares y reglamentos), la Ley General del Sistema Financiero, documentos de Basilea III del BCBS y documentos internos sintéticos con fechas de vigencia distintas. La extracción se realiza con un servicio de ingesta y OCR de documentos del proveedor que defina el Cliente y cada documento se registra con número, fecha de publicación, fecha de entrada en vigencia, estado (vigente, modificada, derogada o sustituida) y relaciones con otras normas. Prueba de entrega: catálogo normativo en un almacén de metadatos (base de datos relacional o analítica) con los metadatos completos de los 25 documentos y reporte de calidad de ingesta.

- **Componente 2 – Recuperación con citación exacta:** indexación por artículo, numeral o disposición con embeddings en un índice vectorial y filtros por metadatos de vigencia; cada fragmento conserva documento, versión, artículo y página. Prueba de entrega: servicio de consulta que devuelve los fragmentos con su cita verificable sobre el conjunto de evaluación del Componente 6.

- **Componente 3 – Agente de respuesta con estado de vigencia e historial de versiones:** agente sobre un modelo de lenguaje de gran escala, intercambiable mediante una capa de abstracción, que responde con la norma vigente, su fecha de entrada en vigencia y la cita exacta; cuando existen versiones anteriores, resume qué cambió y cuándo; cuando no hay sustento en el corpus, lo declara y no responde. Prueba de entrega: agente funcional que responde las 40 preguntas del conjunto de evaluación con el formato definido (respuesta, cita, estado de vigencia, historial de versiones).

- **Componente 4 – Detección de contradicciones y desactualización:** comparación entre versiones de un mismo documento y entre documentos distintos (normativa externa frente a políticas y procedimientos internos), clasificando cada hallazgo como contradicción, documento desactualizado, referencia a norma derogada o vigencia futura, y mostrando las dos citas en conflicto. Prueba de entrega: reporte de hallazgos sobre los casos de demostración de la sección 4.3 con las citas de ambos documentos.

- **Componente 5 – Interfaz de consulta para analistas:** aplicación web desplegable en cualquier nube o entorno del Cliente, con caja de consulta, panel de fuentes citadas con acceso al fragmento original, indicador visual de vigencia, alertas de contradicción y botón de retroalimentación por respuesta. Prueba de entrega: aplicación accesible y demostrada con consultas reales de analistas de riesgo.

- **Componente 6 – Evaluación y trazabilidad:** conjunto de 40 preguntas con respuesta y fuente esperadas (incluye preguntas fuera del corpus y preguntas de control sin contradicción), métricas automatizadas y registro de auditoría de cada consulta (pregunta, fuentes usadas, versión del modelo). Prueba de entrega: informe de evaluación con los resultados frente a los criterios de éxito de la sección 4.4.

- **Componente 7 – Indicador de tiempo ahorrado:** registro por consulta del tiempo que un analista tardaría en resolverla manualmente (línea base por tipo de consulta, validada con analistas del Cliente) frente al tiempo del agente, con un panel en la interfaz que muestra el tiempo ahorrado por consulta, por área usuaria y acumulado. Prueba de entrega: panel de tiempo ahorrado activo y documento de metodología de la línea base, aplicado a los casos de uso de la sección 4.5.

## 4.2 Entregables y Obligaciones de Desempeño

El Consultor entregará los Servicios Incluidos en el Alcance tal como se describe en 4.1. Cada componente representa uno o más entregables definidos y está sujeto a los criterios de aceptación definidos en este documento.

Cada entregable será revisado por el Cliente según los criterios de aceptación establecidos en este documento. Un entregable se considerará aceptado a menos que el Cliente proporcione una notificación por escrito de no conformidad material dentro de los cinco (5) días hábiles posteriores a la entrega. Las solicitudes de aclaración o revisiones menores que no afecten materialmente los criterios de aceptación no retrasan la aceptación.

La aceptación de un entregable confirma la finalización de esa parte de los Servicios y puede activar la facturación de acuerdo con esta SOW.

<table style="width:100%;">
<colgroup>
<col style="width: 18%" />
<col style="width: 44%" />
<col style="width: 27%" />
<col style="width: 9%" />
</colgroup>
<tbody>
<tr>
<td style="text-align: center;"><strong>Componente</strong></td>
<td style="text-align: center;"><strong>Entregable</strong></td>
<td style="text-align: center;"><strong>Criterios de Aceptación</strong></td>
<td style="text-align: center;"><strong>Tarifa</strong></td>
</tr>
<tr>
<td style="text-align: center;">Componente 1</td>
<td style="text-align: center;">Corpus normativo con metadatos de vigencia</td>
<td style="text-align: center;">Catálogo de metadatos con 25 o más documentos; 100% con número, fecha de vigencia, estado y relaciones modifica/deroga completos.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 2</td>
<td style="text-align: center;">Recuperación con citación exacta</td>
<td style="text-align: center;">Cada fragmento devuelto indica documento, versión, artículo y página; la citación es correcta en el 95% o más del conjunto de evaluación.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 3</td>
<td style="text-align: center;">Agente de respuesta con vigencia e historial</td>
<td style="text-align: center;">Las 40 preguntas del conjunto de evaluación se responden con cita, estado de vigencia e historial de versiones cuando existe.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 4</td>
<td style="text-align: center;">Detector de contradicciones y desactualización</td>
<td style="text-align: center;">Detecta al menos 5 de los 6 casos de la sección 4.3, con las dos citas en conflicto, y no más de 1 falso positivo en las preguntas de control.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 5</td>
<td style="text-align: center;">Interfaz web de consulta para analistas</td>
<td style="text-align: center;">Aplicación accesible que muestra respuesta, fuentes, indicador de vigencia y alertas de contradicción, y registra la retroalimentación.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 6</td>
<td style="text-align: center;">Informe de evaluación y registro de auditoría</td>
<td style="text-align: center;">Informe con métricas frente a la sección 4.4 y registro de auditoría del 100% de las consultas realizadas.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td style="text-align: center;">Componente 7</td>
<td style="text-align: center;">Indicador de tiempo ahorrado</td>
<td style="text-align: center;">Panel que muestra, por consulta, área y acumulado, el tiempo humano estimado, el tiempo del agente y el tiempo ahorrado, calculado con la línea base documentada.</td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
<tr>
<td colspan="3" style="text-align: center;"><strong>Obligación Total de Tarifa Fija</strong></td>
<td style="text-align: center;">US$ 0.00</td>
</tr>
</tbody>
</table>

## 4.3 Casos de Demostración de Versiones, Contradicciones y Desactualización

Para demostrar la funcionalidad, el corpus incluirá documentos sintéticos con los siguientes casos sembrados. Las cifras son ilustrativas y no representan la normativa real de la SBS ni de Basilea III.

- **Caso D-1 – Cambio de umbral entre versiones:** el Reglamento sintético de Gestión de Riesgo de Crédito v2019 reclasifica un crédito minorista a “Con Problemas Potenciales” a partir de 60 días de atraso, y la v2023 lo reduce a 30 días. El agente debe responder 30 días citando la v2023, indicar que es la versión vigente e informar que antes era 60 días según la v2019, ya sustituida.

- **Caso D-2 – Procedimiento interno que cita una norma derogada:** el Procedimiento interno de provisiones sigue citando la Circular sintética C-2018, derogada por la C-2022. El agente debe alertar que el procedimiento está desactualizado y citar la norma que la reemplazó.

- **Caso D-3 – Política interna que excede el límite normativo:** la Política de Riesgo de Concentración fija un límite de exposición a un solo deudor de 12% del patrimonio efectivo, mientras la circular vigente fija 10%. El agente debe señalar la contradicción mostrando ambas citas.

- **Caso D-4 – Dos documentos vigentes que se contradicen:** el Manual de Tesorería exige reporte diario de la posición de liquidez y el Procedimiento de Riesgo de Mercado lo exige semanal. El agente debe identificar ambos documentos como vigentes, advertir el conflicto y no elegir uno por su cuenta.

- **Caso D-5 – Norma con vigencia futura:** una circular sintética publicada hoy entra en vigencia el 1 de enero de 2027. Ante una consulta sobre el requisito aplicable hoy, el agente debe distinguir entre la regla vigente actual y la que regirá desde esa fecha.

- **Caso D-6 – Parámetro de capital desactualizado:** la Política de Capital de 2020 usa un colchón de conservación menor al indicado en el documento de Basilea III y en la circular vigente incluidos en el corpus. El agente debe marcar la política como desactualizada y citar la fuente vigente.

## 4.4 Criterios de Éxito del Agente

La solución se considerará exitosa cuando cumpla los siguientes criterios, medidos sobre el conjunto de evaluación de 40 preguntas del Componente 6:

- **Cita exacta:** el 100% de las respuestas incluye documento, versión, artículo y página de la fuente, y la cita corresponde al texto que sustenta la respuesta.

- **Estado de vigencia:** el 100% de las respuestas indica si la norma citada está vigente, modificada, derogada o sustituida, con su fecha de entrada en vigencia.

- **Actualizaciones y versiones anteriores:** en el 90% o más de las consultas sobre normas con versiones previas, la respuesta menciona la versión anterior y resume qué cambió.

- **Contradicciones y desactualización:** el agente detecta al menos 5 de los 6 casos sembrados de la sección 4.3, y genera no más de 1 falso positivo en las preguntas de control.

- **Exactitud:** al menos 85% de las respuestas es validado como correcto por un analista de Riesgos o Cumplimiento designado por el Cliente.

- **Sin invención:** en el 100% de las preguntas fuera del corpus el agente indica que no encontró sustento y no inventa una norma o cláusula.

- **Tiempo ahorrado:** la reducción del tiempo por consulta frente a la línea base humana es de al menos 70% en cada uno de los casos de uso de la sección 4.5, y el indicador la muestra por área usuaria y acumulada.

- **Trazabilidad:** el 100% de las consultas queda registrado con pregunta, fuentes usadas y versión del modelo.

## 4.5 Casos de Uso Sintéticos de Demostración y Tiempo Ahorrado

Cada caso se ejecutará en vivo sobre el corpus de prueba. El área usuaria es la que formula la consulta; los tiempos de línea base (minutos que un analista tarda hoy en buscar, leer y consultar a un colega) son supuestos sintéticos que se validarán con analistas del Cliente.

<table style="width:100%;">
<colgroup>
<col style="width: 18%" />
<col style="width: 27%" />
<col style="width: 37%" />
<col style="width: 17%" />
</colgroup>
<tbody>
<tr>
<td style="text-align: center;"><strong>Caso y área usuaria</strong></td>
<td style="text-align: center;"><strong>Consulta del analista</strong></td>
<td style="text-align: center;"><strong>Respuesta esperada del agente</strong></td>
<td style="text-align: center;"><strong>Min: humano → agente</strong></td>
</tr>
<tr>
<td style="text-align: center;">U-1 – Riesgo de Crédito</td>
<td style="text-align: center;">¿Desde cuántos días de atraso se reclasifica un crédito minorista a “Con Problemas Potenciales”?</td>
<td style="text-align: center;">30 días según el Reglamento v2023 (vigente, artículo citado); advierte que en la v2019, sustituida, eran 60 días.</td>
<td style="text-align: center;">30 → 1</td>
</tr>
<tr>
<td style="text-align: center;">U-2 – Riesgo de Crédito (Provisiones)</td>
<td style="text-align: center;">¿Qué circular sustenta el cálculo de provisiones del procedimiento interno?</td>
<td style="text-align: center;">Alerta que el procedimiento cita la Circular C-2018, derogada por la C-2022, e indica la norma vigente.</td>
<td style="text-align: center;">35 → 2</td>
</tr>
<tr>
<td style="text-align: center;">U-3 – Riesgos (Concentración)</td>
<td style="text-align: center;">¿Cuál es el límite de exposición a un solo deudor?</td>
<td style="text-align: center;">10% del patrimonio efectivo según la circular vigente; señala que la política interna dice 12% y muestra ambas citas.</td>
<td style="text-align: center;">45 → 2</td>
</tr>
<tr>
<td style="text-align: center;">U-4 – Tesorería (Riesgo de Liquidez)</td>
<td style="text-align: center;">¿Con qué frecuencia se reporta la posición de liquidez?</td>
<td style="text-align: center;">Detecta conflicto entre dos documentos vigentes (diario en el Manual de Tesorería, semanal en el Procedimiento de Riesgo de Mercado) y recomienda escalarlo.</td>
<td style="text-align: center;">30 → 2</td>
</tr>
<tr>
<td style="text-align: center;">U-5 – Cumplimiento Normativo</td>
<td style="text-align: center;">¿Qué requisito de reporte aplica hoy y cuál desde el 1 de enero de 2027?</td>
<td style="text-align: center;">Indica la regla vigente hoy y la que regirá desde el 1 de enero de 2027, con ambas citas.</td>
<td style="text-align: center;">25 → 1</td>
</tr>
<tr>
<td style="text-align: center;">U-6 – Riesgos (Capital)</td>
<td style="text-align: center;">¿Qué colchón de conservación de capital debemos usar?</td>
<td style="text-align: center;">Marca la Política de Capital de 2020 como desactualizada y cita el documento de Basilea III y la circular vigentes.</td>
<td style="text-align: center;">40 → 2</td>
</tr>
<tr>
<td style="text-align: center;">U-7 – Cumplimiento Normativo (fuera del corpus)</td>
<td style="text-align: center;">¿Qué establece la normativa sobre criptoactivos en banca?</td>
<td style="text-align: center;">Indica que no encontró sustento en el corpus y no inventa una norma.</td>
<td style="text-align: center;">20 → 1</td>
</tr>
<tr>
<td colspan="3" style="text-align: center;"><strong>Tiempo ahorrado en los 7 casos</strong></td>
<td style="text-align: center;">225 → 11 (214 min, 95%)</td>
</tr>
</tbody>
</table>

## 5. Enfoque de Entrega

El Consultor realizará los Servicios utilizando un enfoque de entrega estructurado y centrado en los resultados, apropiado para compromisos de tarifa fija. Los componentes se construirán de forma iterativa sobre el corpus de prueba y se validarán con analistas designados por el Cliente contra el conjunto de evaluación del Componente 6.

## 6. Roles y Responsabilidades

## 6.1 Responsabilidades del Consultor

- Proporcionar personal calificado con las habilidades y experiencia adecuadas

- Entregar los servicios de manera profesional y competente

- Cumplir con los entregables y las obligaciones de desempeño definidos

- Comunicar riesgos, suposiciones y dependencias

## 6.2 Responsabilidades del Cliente

- Proporcionar acceso oportuno a sistemas, datos y partes interesadas

- Designar un punto de contacto principal con autoridad de decisión

- Proporcionar revisiones, comentarios y decisiones de aceptación oportunas

- Cumplir con las obligaciones de pago de acuerdo con esta SOW

- Designar al menos un analista de Riesgos o Cumplimiento que valide las respuestas del conjunto de evaluación y confirme los casos de la sección 4.3

# 7. Tarifas y Estructura de Pago

## 7.1 Resumen de Tarifa

La tarifa total por los Servicios bajo esta SOW es de US\$ 0.00 (la "Tarifa Fija"), por tratarse de un documento sintético preparado para una hackathon sin valor comercial. La Tarifa Fija se basa en el alcance, las suposiciones y los entregables definidos en esta SOW. La Tarifa Fija no incluye impuestos, retenciones o ningún otro gravamen aplicable a pagos al Consultor, los cuales deberán ser pagados por el Cliente de acuerdo a la ley vigente.

## <span class="mark">7.2 Facturación de Tarifa Fija</span>

<span class="mark">La Tarifa Fija se facturará como un único monto al finalizar y aceptar los Servicios de acuerdo con la Sección 4.2 (Entregables y Aceptación) y la Sección 10 (Aceptación).</span>

La Tarifa Fija se basa en el alcance, las suposiciones y los entregables descritos en esta SOW. La aceptación del Cliente confirma la finalización de los Servicios a efectos de facturación.

## 7.3 Exclusiones

Todos los cargos excluyen cualquier impuesto federal, estatal, provincial, municipal o extranjero aplicable, así como aranceles, tarifas, gravámenes, retenciones o evaluaciones gubernamentales similares de cualquier tipo, incluidos, entre otros, el impuesto sobre las ventas (sales tax), el impuesto sobre el uso (use tax), el impuesto al valor agregado (IVA), el impuesto sobre bienes y servicios (GST), impuestos especiales, derechos de aduana, impuestos sobre servicios digitales y cualquier impuesto de retención (denominados colectivamente como "Impuestos").

El Cliente será el único responsable de todos los Impuestos aplicados en relación con los Servicios, a excepción de los impuestos basados únicamente en los ingresos netos del Consultor. El Consultor podrá facturar y recaudar los Impuestos aplicables según lo exija la ley.

Si la legislación aplicable exige que el Cliente retenga o descuente cualquier parte del pago (incluidas las retenciones de IVA o las retenciones de impuestos sobre la renta), el Cliente deberá incrementar el monto del pago (**gross up**) de modo que el Consultor reciba el importe total que habría recibido en ausencia de dicha retención. El Cliente deberá proporcionar documentación oficial que acredite cualquier retención o remesa de impuestos requerida.

Cualquier Impuesto nuevo o incrementado que se imponga después de la Fecha de Entrada en Vigor y que se aplique a los Servicios será responsabilidad del Cliente.

# 8. Depósito

## <span class="mark">8.1 Depósito de Compromiso</span>

<span class="mark">Este compromiso no requiere un depósito por adelantado.</span>

# 9. Facturación y Condiciones de Pago

## 9.1 Facturación

Las facturas se emitirán de acuerdo con la estructura de facturación definida en las Secciones 4.2 y 7.

## 9.2 Condiciones de Pago, Intereses y Cargos Administrativos

Las facturas vencen quince (15) días a partir de la fecha de la factura, a menos que se indique lo contrario.Net 15

Cualquier monto no disputado que no se pague a su vencimiento devengará intereses a partir del día inmediatamente siguiente a la expiración de las condiciones de pago a una tasa del uno y medio por ciento (1.5%) por mes, compuesto mensualmente, o la tasa máxima permitida por la ley, lo que sea menor.

Cualquier monto de factura no disputado que permanezca impago más de treinta (30) días después de su fecha de vencimiento puede estar sujeto a un cargo administrativo único de \$50.00 para cubrir los esfuerzos de cobro y administrativos.

El Consultor se reserva el derecho de suspender los Servicios por pago atrasado o falta de pago.

# 10. Aceptación

Cada entregable y componente bajo esta SOW será revisado y aceptado independientemente.

El rechazo, la no aceptación o la disputa del Cliente de cualquier entregable o componente individual no retrasará, suspenderá ni afectará la obligación del Cliente de revisar, aceptar y pagar cualquier otro entregable o componente que se complete y acepte de acuerdo con esta SOW.

Los honorarios asociados con los entregables o componentes aceptados siguen siendo pagaderos y exigibles independientemente del estado de cualquier otro entregable o componente.

El Cliente dispondrá de un plazo de cinco (5) Días Hábiles contados a partir de la notificación de la finalización de un Componente para disputar por escrito, mediante correo electrónico, la aceptación del mismo. En ausencia de una comunicación expresa disputando la entrega del Componente dentro del plazo estipulado, el Componente se considerará aceptado a todos los efectos del presente SOW.

# 11. Gestión de Cambios

Cualquier cambio en el alcance, los entregables o las suposiciones debe documentarse en una orden de cambio por escrito o una SOW enmendada ejecutada por ambas partes.

# 12. Terminación

Si el Cliente rescinde esta SOW por conveniencia:

- El Cliente sigue siendo responsable del pago de todos los entregables y componentes aceptados

- Los honorarios por entregables o componentes completados y aceptados no son reembolsables

# <span class="mark">13. Suposiciones y Dependencias</span>

Esta SOW asume que:

- **Propiedad Intelectual, Metodología del Consultor, y Uso de IA Generativa:** FluentData utiliza su Propiedad Intelectual (PI), IA Generativa, y patrones de entrega establecidos para optimizar los Servicios, lo cual se tiene en cuenta en el precio de Tarifa Fija. Cualquier requisito, decisión o solicitud del Cliente que impida o contradiga materialmente la capacidad del Consultor para aprovechar esta PI y metodología puede requerir una Orden de Cambio por escrito y un posible ajuste de tarifas y/o plazos.

- Participación oportuna del Cliente y acceso a los sistemas y recursos requeridos

  - El Cliente debe proporcionar el corpus normativo vigente y sus versiones históricas acordadas, así como los documentos internos sintéticos o de ejemplo, dentro de los 3 días hábiles posteriores a la firma

  - El Cliente confirma el proveedor de nube y el modelo de lenguaje a utilizar, o autoriza al Consultor a proponer una arquitectura de referencia equivalente; la solución no depende de un proveedor específico

  - Los tiempos de línea base del indicador de tiempo ahorrado se validan con analistas del Cliente antes de la demostración

  - El corpus de la hackathon se compone de normativa pública y documentos sintéticos; no incluye documentos internos reales ni confidenciales del BCP

  - La normativa pública se incorpora en la versión publicada por la SBS y por el BCBS a la fecha de carga; la actualización posterior del corpus no está incluida

  - El agente es una herramienta de apoyo a la consulta y no reemplaza el criterio ni el dictamen de las áreas de Cumplimiento y Asesoría Legal del Cliente

- Disponibilidad de las partes interesadas del Cliente para revisiones y aceptación

- Ausencia de cambios materiales en las suposiciones fundamentales

- Planificación de proyectos y reuniones con el Cliente hasta cuatro (4) horas por semana

El incumplimiento de estas suposiciones puede afectar la entrega de los componentes y puede requerir una orden de cambio con tarifas adicionales.

# <span class="mark">14. Fuera de Alcance</span>

A menos que se acuerde explícitamente por escrito, lo siguiente está fuera del alcance:

- Adquisición de hardware, software o consumo

- Suministro de hardware o actualizaciones de dispositivos del lado del cliente

- Limpieza o remediación manual de datos

- Digitalización manual de documentos físicos en papel (escaneo)

- Reescritura de políticas existentes (la IA ingerirá, no será autora del contenido legal original).

- Tarifas de licencia de terceros

- Trabajo fuera de la capacidad de sprint acordada

- Reuniones adicionales con el Cliente fuera de las definidas en la sección 13

- Integración con sistemas core, de producción o de autenticación del Cliente, y puesta en producción o soporte operativo del agente

- Dictámenes u opiniones legales oficiales sobre la interpretación de la normativa

- Cobertura de normativa fuera del corpus acordado en el Componente 1, y actualización automática del corpus ante nuevas publicaciones

- Procesamiento de documentos internos reales o confidenciales del Cliente

- Entrenamiento o ajuste fino (fine-tuning) de modelos de lenguaje

- Cualquier funcionalidad no descrita explícitamente en la sección 4.1

# 15. Aceptación y Firmas

Al ejecutar esta SOW, las partes acuerdan los términos y el modelo de entrega descritos en este documento.

Por el Consultor FluentData, INC

Firma: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Nombre: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Título: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Fecha: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Por el Cliente Banco de Crédito del Perú (BCP)

Firma: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Nombre: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Título: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Fecha: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
