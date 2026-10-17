# Validación del agente con 40 preguntas del corpus real (2026-10-17)

Archivos: `Preguntas_40_corpus.csv` (las preguntas), `Respuestas_40_preguntas_corpus_validadas.csv` (cada respuesta con su calificación) y
`.json` (las métricas). Corrió el agente desplegado (gpt-5-mini, escala a gpt-5), sobre las 17 normas reales, sin sintético.

## Preguntas

34 con respuesta: dos chunks reales por norma, con semilla fija, y gpt-5-mini escribió una pregunta que ese chunk responde (etiqueta *silver*).
6 negativas escritas a mano sobre temas que el corpus no cubre (tasa máxima hipotecaria, ITF, financiamiento participativo, encaje, leasing, criptoactivos).

## Criterio (simple y definido)

Una respuesta es **confiable** si cumple los cuatro:

| Criterio | Quién lo mide | Qué exige |
|---|---|---|
| citas | código | al menos una cita y todas son tramo literal verificado del chunk |
| respaldo | juez | toda afirmación está en los textos citados (parafrasear sí, agregar hechos no) |
| responde | juez | contesta lo que se pregunta |
| (negativas) | código | se abstiene; si afirma algo es alucinación |

El juez es Claude (otra familia que el modelo que responde), en dos partes en paralelo, y ve solo la respuesta y los textos citados.

## Resultado

| Métrica | Valor |
|---|---|
| **Respuestas confiables** | **67,5 %** (27 de 40), IC 95 % de 52,5 a 82,5 |
| Positivas confiables | 67,6 % (23 de 34) |
| Citas verificadas (de lo respondido) | 96,9 % |
| Respaldo por el juez | 81,2 % |
| Responde lo pedido | 81,2 % |
| Cita el artículo de origen (silver) | 93,8 % |
| Abstenciones falsas | 2 de 34 (p29, p30) |
| Negativas abstenidas | 4 de 6 (afirmaron: p35, p39) |
| **Alucinación** (afirma algo que no está en lo citado) | **20,6 %** de lo respondido |
| Costo de las 40 | 0,31 USD; p50 24 s, p95 38 s |

## Regla de distancia (para no responder fuera del corpus)

evidencia = promedio del coseno de los 6 fragmentos más cercanos a la pregunta (el mejor de todas las búsquedas); distancia = 1 − evidencia.
Umbral calibrado con estas corridas: percentil 5 de 23 positivas de desarrollo (las 11 reservadas no entran) → **evidencia mínima 0,628,
distancia máxima 0,372**, AUC 0,897. Aplicada a estas 40: las **6 de 6 negativas** se abstienen; se pierden 2 positivas buenas (p05, p23);
0 de 11 reservadas perdidas. El total confiable queda igual (67,5 %), pero ya no responde nada fuera del corpus. Activa en el despliegue.

## Lo que falla (para mejorar)

- **Agrega hechos dentro del tema (6 casos: p02, p12, p19, p20, p27, p32).** La regla de distancia no los ve: el tema sí está en el corpus.
  Siguiente paso: verificar cada oración contra su cita con NLI (RoBERTa XNLI) o un verificador, y corregir o quitar lo no respaldado.
- **p09** respondió solo «Leeré el artículo 127…»: corregido (la verificación ahora rechaza respuestas que narran en vez de responder).
- **p08** no pasó la verificación dos veces y entregó solo fuentes; **p11** respondió otra fecha de vigencia que la esperada.
- **p29, p30** se abstuvieron teniendo respuesta: son artículos modificados (16 y 21) en normas con problemas de extracción (auditoría del corpus).
