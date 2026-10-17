# Principios: lo que un modelo puede y no puede hacer aquí

1. **El modelo no es la fuente de verdad; el texto de la norma lo es.** Toda afirmación nace de un chunk recuperado
   y se cita literal. Lo que no está en un chunk visto no se afirma.
2. **Solo cita lo que vio.** Cada `chunk_id` citado debe estar en `seen` (los chunks que la corrida leyó). Citar un
   artículo de memoria, aunque sea correcto, se rechaza.
3. **La cita es literal.** `quote in chunk.text` tras normalizar espacios. Parafrasear dentro de las comillas es una
   falta (`quote_altered`).
4. **Los números salen del texto, nunca del modelo.** Plazos, montos, porcentajes y fechas se copian de la cita; si
   la respuesta trae un número que no está en la cita, es `foreign_fact`.
5. **La vigencia la decide el código.** El modelo recibe la versión que corresponde a `as_of` y la historia; no
   decide qué versión está vigente ni interpreta «entra en vigencia».
6. **Abstenerse es una respuesta válida y a veces la mejor.** Sin evidencia confirmada no hay síntesis. La abstención
   dice qué se buscó y qué fue lo más cercano.
7. **El modelo propone; el código verifica; la persona decide lo riesgoso.** Ninguna salida del modelo se muestra
   sin pasar por `verify`; ninguna acción irreversible ocurre sin una persona.
8. **Salida estructurada o nada.** El modelo responde con el esquema acordado. Inválida se reintenta con el error a
   la vista; a la tercera queda `rejected`. Nunca se rellena un campo con un valor por defecto: sería un veredicto
   inventado.
9. **No opina sobre derecho.** Ordena, cita y relaciona. «Qué debería hacer el banco» es de la persona; el modelo
   puede listar los artículos que aplican.
10. **Todo queda registrado.** Modelo, versión del prompt, chunks vistos, citas, faltas, costo y quién aprobó. Un
    resultado sin ledger no existe.

Estas reglas las hace cumplir el código (`verify`, `risk`, `ledger`) y se prueban sin modelo con un proveedor falso.
Si un prompt necesita saltarse una, el diseño está mal: se corrige el diseño, no el prompt.
