# Riesgo: cuándo entra una persona

La pausa humana es una propiedad del tipo de caso, declarada como dato (`backend/seeds/risk_rules.csv`), no una
decisión del prompt. El nodo `risk` evalúa las reglas en orden; la primera que aplica gana. Si el modelo sugiere
menos riesgo que la regla, gana la regla.

| orden | condición | nivel | por qué |
|---|---|---|---|
| 1 | `verify` devolvió alguna falta tras los reintentos | `rejected` (no se muestra) | nunca una respuesta no verificada |
| 2 | escenario `policy_vs_norm` o `impact` | `approve` | afirmar que el banco cumple o incumple es irreversible en la práctica |
| 3 | alguna cita es de una versión no vigente a `as_of` | `approve` | la persona confirma que la fecha pedida es la correcta |
| 4 | escenario `threshold` (plazo, monto, porcentaje) | `notify` | un número mal leído cuesta; se muestra con aviso |
| 5 | abstención | `notify` | para detectar normas que faltan en el corpus |
| 6 | el modelo marcó `risk_hint = high` | `notify` | la sugerencia del modelo solo sube, nunca baja |
| 7 | resto | `auto` | |

Niveles:
- `auto`: se entrega y se registra.
- `notify`: se entrega con marca visible y queda en la bandeja de revisión posterior.
- `approve`: `interrupt`; la respuesta queda `pending_human` con la evidencia lista; la persona acepta, edita o
  rechaza (`HumanResponse`), y su decisión se guarda como dato para recalibrar.

Un escenario pasa de `approve` a `notify`, o de `notify` a `auto`, solo cuando el límite inferior del intervalo de su
precisión sobre el golden reservado supera el umbral fijado por quien lleva el proyecto (`docs/10-evaluation.md`).
