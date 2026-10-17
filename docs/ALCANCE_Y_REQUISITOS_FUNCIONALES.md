# Alcance del Proyecto, Requisitos Funcionales y Fuentes Oficiales
**Proyecto:** RegulaBank Agent — Agente de Normativa y Políticas Internas  
**Entorno de Aplicación:** Banco de Crédito del Perú (BCP) — Caso de Estudio Hackathon  
**Áreas Usuarias:** Riesgos (Crédito, Mercado, Liquidez, Operacional) y Cumplimiento Normativo  
**Estado:** Documento Funcional Agnóstico de Tecnología (Stack Neutral)

---

## 1. Contexto de Negocio y Definición del Problema

### 1.1 Contexto Operativo
El banco opera en un entorno donde las políticas internas de riesgo, circulares y resoluciones de la **Superintendencia de Banca, Seguros y AFP (SBS)**, lineamientos de **Basilea III** y procedimientos operativos residen dispersos en múltiples documentos, versiones y áreas (Riesgos, Cumplimiento Normativo, Tesorería y Operaciones). 

Actualmente, cuando un analista necesita resolver una duda normativa:
* Consulta informalmente a colegas o revisa manualmente extensos documentos PDF.
* Carece de una vista unificada sobre qué norma está vigente, qué resolución modificatoria la alteró y qué documentos o políticas internas aún citan versiones derogadas.

### 1.2 Desafíos Específicos
1. **Búsqueda lenta en documentos dispersos:** La información normativa y procedimental vive en documentos extensos de distintas áreas; localizar la cláusula aplicable consume tiempo operativo crítico de análisis de riesgo.
2. **Vigencia incierta:** Coexisten versiones de una misma circular o reglamento sin una fuente única que valide cuál rige a una fecha específica, provocando que se tomen decisiones basadas en artículos modificados o derogados.
3. **Interpretaciones inconsistentes:** Distintos analistas emiten criterios divergentes sobre una misma norma al consultar fuentes o versiones no sincronizadas.
4. **Contradicciones normativas no detectadas:** Políticas y manuales internos pueden contradecir regulaciones vigentes o exceder límites prudenciales sin ser advertidos hasta auditorías o inspecciones del regulador.
5. **Riesgo y pérdida de productividad:** Riesgo operativo y regulatorio ante observaciones de la SBS, sumado a la pérdida acumulada de cientos de horas hombre por consultas repetitivas.

---

## 2. Inventario de Fuentes y Corpus Normativo

El corpus del sistema debe cubrir un **mínimo de 25 documentos**, estructurados entre normativa pública oficial del sistema financiero peruano, estándares internacionales y políticas internas sintéticas.

### 2.1 Normativa Peruana del Sistema Financiero
* **Ley General:** Ley 26702 (Ley General del Sistema Financiero y Orgánica de la SBS).
* **Adecuación a Basilea III:** Decreto Legislativo N.° 1531 (modificatoria de la Ley 26702).
* **Gestión de Riesgo de Liquidez:**
  * Resolución SBS 9075-2012 (Reglamento de Gestión de Riesgo de Liquidez).
  * Resolución SBS 3296-2022 (Actualización de Ratio de Cobertura de Liquidez - RCL).
  * Resolución SBS 4221-2023 (Ratio de Fondeo Neto Estable - RFNE).
* **Gestión de Riesgo de Crédito y Provisiones:**
  * Resolución SBS 11356-2008 (Reglamento para la Evaluación y Clasificación del Deudor y Exigencia de Provisiones) y sus modificatorias.
* **Gestión de Riesgo de Mercado:**
  * Reglamento de Sensibilidades y Valor en Riesgo (VaR) de la SBS.
* **Gestión de Riesgo Operacional:**
  * Reglamento de Gestión de Riesgo Operacional (Resolución SBS 272-2017 y conexas).
* **Prevención de Lavado de Activos y Financiamiento del Terrorismo (LA/FT):**
  * Resolución SBS 2660-2015 (Reglamento de Gestión de Riesgo de LA/FT) y normativa UIF-Perú.
* **Seguridad de la Información y Continuidad:**
  * Resolución SBS 504-2021 (Reglamento de Seguridad de la Información y Ciberseguridad).
  * Reglamento de Tercerización de Servicios de la SBS.
* **Protección de Datos y Conducta de Mercado:**
  * Ley 29733 (Ley de Protección de Datos Personales) y su Reglamento.
  * Normas de Conducta de Mercado y Medios de Pago de la SBS.
* **Normativa BCRP:**
  * Circulares de Encaje Legal, Sistemas de Liquidación y Compensación de Pagos.

### 2.2 Normativa y Estándares Internacionales (Referenciales)
* **Comité de Basilea (BCBS):** Lineamientos de Basilea III (capital, colchones de conservación, apalancamiento).
* **BCBS Riesgo Operacional e IA:** Principios de gestión de riesgo operacional vinculados a modelos y agentes automatizados.
* **GAFI / FATF:** Recomendaciones internacionales contra el lavado de activos.
* **Estándares ISO/IEC:** ISO 27001 (Seguridad de la Información) e ISO 22301 (Continuidad de Negocio).
* **EU AI Act:** Marco de referencia para sistemas y agentes de inteligencia artificial en entornos regulados.

### 2.3 Documentación Interna Sintética del Banco
* Manual de Tesorería.
* Política de Riesgo de Concentración de Crédito.
* Política de Gestión de Capital.
* Procedimiento de Clasificación de Deudores y Provisiones.
* Procedimiento de Gestión de Riesgo de Mercado.

---

## 3. Alcance Funcional: Los 7 Componentes del Agente

El sistema se estructura en 7 componentes funcionales independientes de la infraestructura subyacente:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      COMPONENTES DEL SISTEMA                           │
├──────────────────────────┬─────────────────────────────────────────────┤
│ 1. Corpus y Metadatos    │ 25+ documentos, vigencia, relaciones        │
│ 2. Recuperación Exacta   │ Cita verificable: doc, versión, art., pág.  │
│ 3. Agente de Respuesta   │ Respuesta vigente + resumen de historial    │
│ 4. Detector Conflictos   │ Contradicciones, desactualización y normas  │
│ 5. Interfaz Analistas    │ Chat, panel de vigencia, alertas y feedback │
│ 6. Evaluación & Auditoría│ 40 preguntas golden, traza completa         │
│ 7. Tiempo Ahorrado       │ Panel métrico de reducción de tiempo (min)  │
└──────────────────────────┴─────────────────────────────────────────────┘
```

### Componente 1: Corpus Normativo con Metadatos de Vigencia
* Ingesta y catálogo de un corpus de 25 o más documentos.
* Cada documento y fragmento se estructura con:
  * Número oficial y emisor (SBS, BCRP, Congreso, Banco).
  * Fecha de publicación y fecha de entrada en vigencia (`valid_from`).
  * Estado normativo: `vigente`, `modificada`, `derogada` o `sustituida`.
  * Fecha de fin de vigencia (`valid_to`), en caso aplique.
  * Relaciones explícitas de cambio entre normas: `MODIFIES`, `REPEALS`, `REPLACES`, `ADDS`, `IMPLEMENTS`.

### Componente 2: Recuperación con Citación Exacta
* Indexación a nivel granular (artículo, numeral o cláusula).
* Cada fragmento recuperado mantiene su procedencia inalterable: documento, versión, artículo, numeral y número de página original.
* Capacidad de responder con citas literales contrastables sobre el texto fuente.

### Componente 3: Agente de Respuesta con Vigencia e Historial
* Responde la consulta en lenguaje natural identificando con precisión la norma aplicable al momento de la consulta (`as_of`).
* Si la norma sufrió modificaciones previas, resume qué cambió respecto a versiones anteriores y desde qué fecha.
* **Control estricto de no-invención:** Si una consulta no encuentra sustento en el corpus cargado, el agente se abstiene explícitamente y declara no haber encontrado evidencia, sin fabricar normas ni cláusulas.

### Componente 4: Detector de Contradicciones y Desactualización
* Comparación sistemática entre versiones de una misma norma y entre normativa externa vs. políticas/procedimientos internos.
* Categorización de hallazgos en 4 tipologías:
  1. **Contradicción directa:** Una política interna fija reglas o umbrales que vulneran una norma vigente.
  2. **Documento desactualizado:** Un procedimiento interno calcula parámetros con reglas obsoletas.
  3. **Referencia a norma derogada:** Un procedimiento interno cita formalmente una resolución o circular derogada.
  4. **Vigencia futura:** Distinción explícita entre lo que rige hoy y lo que entrará en vigor en una fecha posterior.
* El detector presenta siempre **ambas citas en conflicto** lado a lado para la decisión del analista o revisor humano.

### Componente 5: Interfaz de Consulta para Analistas
* Aplicación interactiva con:
  * Caja de consulta en lenguaje natural y selector de fecha de vigencia de análisis (`as_of`).
  * Respuestas con citas literales resaltadas y acceso directo a la fuente original.
  * Banderas visuales de vigencia (`Vigente`, `Modificada`, `Derogada`).
  * Alertas visuales destacadas ante contradicciones detectadas.
  * Mecanismo de retroalimentación de analistas (validar / rechazar / retroalimentar).

### Componente 6: Evaluación y Trazabilidad
* Banco formal de **40 preguntas de evaluación** con respuesta y fuentes esperadas (incluye preguntas de vigencia temporal, preguntas fuera de corpus y preguntas de control negativo).
* Registro de auditoría (ledger) inmutable de cada consulta: pregunta formulada, fragmentos/artículos consultados, citas verificadas, versión del sistema y latencia.

### Componente 7: Indicador de Tiempo Ahorrado (Métrica de Valor de Negocio)
* Medición en tiempo real del tiempo que un analista humano tardaría en resolver la consulta de forma manual frente al tiempo de respuesta del agente.
* Panel en la interfaz que reporta:
  * Tiempo humano estimado (según línea base documentada por caso).
  * Tiempo real de respuesta del agente (segundos).
  * **Tiempo neto ahorrado:** por consulta individual, por área usuaria y total acumulado.

---

## 4. Casos Sembrados de Demostración (D-1 a D-6)

Para demostrar las capacidades de detección y versionamiento, el corpus incluye los siguientes 6 casos estructurados:

| Caso | Tipo de Conflicto | Escenario y Comportamiento Esperado del Agente |
|---|---|---|
| **D-1** | **Cambio de umbral entre versiones** | El *Reglamento de Riesgo de Crédito v2019* reclasificaba a "Con Problemas Potenciales" (CPP) a partir de 60 días de atraso; la versión *v2023* lo redujo a 30 días.<br>👉 **Esperado:** El agente responde 30 días citando la v2023 vigente, e informa explícitamente que antes eran 60 días según la v2019 ya sustituida. |
| **D-2** | **Cita a norma derogada en procedimiento** | El *Procedimiento Interno de Provisiones* sigue citando la *Circular C-2018*, la cual fue expresamente derogada por la *Circular C-2022*.<br>👉 **Esperado:** El agente alerta que el procedimiento interno está desactualizado y cita la norma vigente que reemplazó a la derogada. |
| **D-3** | **Política interna que excede límite normativo** | La *Política de Concentración de Riesgo* fija un límite de exposición a un solo deudor del 12% del patrimonio efectivo, mientras que la circular regulatoria vigente fija como tope el 10%.<br>👉 **Esperado:** El agente señala la contradicción regulatoria mostrando ambas citas textuales en conflicto. |
| **D-4** | **Dos documentos internos vigentes en conflicto** | El *Manual de Tesorería* exige reporte diario de la posición de liquidez; el *Procedimiento de Riesgo de Mercado* exige reporte semanal.<br>👉 **Esperado:** El agente identifica que ambos documentos internos están marcados como vigentes, advierte el conflicto y recomienda su escalamiento sin elegir arbitrariamente. |
| **D-5** | **Norma con vigencia futura** | Una circular regulatoria publicada recientemente fija entrada en vigencia a partir del 1 de enero de 2027.<br>👉 **Esperado:** Ante una consulta sobre el requisito exigible hoy, el agente diferencia con claridad entre la regla vigente actual y la que entrará a regir en 2027. |
| **D-6** | **Parámetro de capital desactualizado** | La *Política de Capital 2020* utiliza un colchón de conservación menor al estipulado en los estándares vigentes de Basilea III y circulares correspondientes.<br>👉 **Esperado:** El agente marca la política interna como desactualizada y cita la fuente normativa vigente. |

---

## 5. Casos de Uso de Demostración y Línea Base de Tiempo Ahorrado

La siguiente matriz documenta los 7 casos de demostración evaluados en vivo con sus tiempos comparativos:

| Caso | Área Usuaria | Consulta del Analista | Respuesta Esperada del Agente | Tiempo Humano | Tiempo Agente | Tiempo Ahorrado | % Ahorro |
|---|---|---|---|:---:|:---:|:---:|:---:|
| **U-1** | Riesgo de Crédito | *¿Desde cuántos días de atraso se reclasifica un crédito minorista a "Con Problemas Potenciales"?* | 30 días según Reglamento v2023 vigente (artículo citado); advierte que en v2019 sustituida eran 60 días. | 30 min | 1 min | **29 min** | 97% |
| **U-2** | Riesgo de Crédito (Provisiones) | *¿Qué circular sustenta el cálculo de provisiones del procedimiento interno?* | Alerta que el procedimiento cita la Circular C-2018 (derogada por C-2022) e indica la norma vigente. | 35 min | 2 min | **33 min** | 94% |
| **U-3** | Riesgos (Concentración) | *¿Cuál es el límite de exposición a un solo deudor?* | 10% del patrimonio efectivo según circular vigente; señala que la política interna dice 12% y muestra ambas citas. | 45 min | 2 min | **43 min** | 96% |
| **U-4** | Tesorería (Riesgo Liquidez) | *¿Con qué frecuencia se reporta la posición de liquidez?* | Detecta conflicto entre documentos vigentes (diario en Tesorería vs. semanal en Riesgo de Mercado) y recomienda escalar. | 30 min | 2 min | **28 min** | 93% |
| **U-5** | Cumplimiento Normativo | *¿Qué requisito de reporte aplica hoy y cuál desde el 1 de enero de 2027?* | Indica la regla vigente hoy y la que regirá desde 2027, con ambas citas y fechas. | 25 min | 1 min | **24 min** | 96% |
| **U-6** | Riesgos (Capital) | *¿Qué colchón de conservación de capital debemos usar?* | Marca Política de Capital 2020 como desactualizada y cita Basilea III / circular vigente. | 40 min | 2 min | **38 min** | 95% |
| **U-7** | Cumplimiento (Fuera de Corpus) | *¿Qué establece la normativa sobre criptoactivos en banca?* | Declara no haber encontrado sustento en el corpus y se abstiene de inventar norma o respuesta. | 20 min | 1 min | **19 min** | 95% |
| **TOTAL**| **Múltiples Áreas** | **7 Casos de Negocio Evaluados** | **Demostración integral de valor y trazabilidad** | **225 min** | **11 min** | **214 min** | **95.1%** |

---

## 6. Criterios de Éxito y Aceptación

Para considerar exitosa la solución, deben cumplirse las siguientes métricas sobre el conjunto de evaluación:

1. **Cita exacta (100%):** La totalidad de respuestas debe incluir documento, versión, artículo y página verificable de la fuente.
2. **Estado de vigencia (100%):** Toda respuesta debe declarar si la norma está vigente, modificada, derogada o con vigencia futura, con su fecha de vigencia.
3. **Resumen de versiones previas ($\ge 90\%$):** En normas que sufrieron modificaciones, el agente debe resumir qué cambió y cuándo.
4. **Detección de contradicciones ($\ge 5$ de 6 casos):** Identificar al menos 5 de los 6 casos sembrados de la sección 4, con no más de 1 falso positivo en preguntas de control.
5. **Exactitud validada ($\ge 85\%$):** Las respuestas deben ser aprobadas como técnicamente correctas por especialistas de Riesgos y Cumplimiento.
6. **Cero alucinaciones / invención (100%):** En el 100% de preguntas sin respuesta en el corpus, el agente debe abstenerse limpiamente.
7. **Reducción de tiempo ($\ge 70\%$):** Demostrar una reducción superior al 70% en cada uno de los casos frente a la línea base humana.
8. **Trazabilidad completa (100%):** Cada consulta debe quedar auditada en el log con pregunta, fuentes utilizadas y tiempo registrado.

---

## 7. Límites y Fuera de Alcance

Para mantener el foco del proyecto, quedan expresamente excluidos los siguientes puntos:
* **Dictámenes u opiniones legales formales:** El agente es una herramienta de asistencia y recuperación documental; la interpretación legal vinculante recae en los analistas y asesores legales humanos.
* **Uso de datos confidenciales o reales del banco:** La solución se basa exclusivamente en normativa pública y políticas internas sintéticas.
* **Reescritura de políticas:** El sistema diagnostica y detecta desalineaciones, pero no redacta nuevas políticas aprobadas.
* **Integración con sistemas core bancarios transaccionales:** La demo opera como un sistema autónomo de consulta y auditoría sin conexión a los cores transaccionales del banco.
