# charter: cómo se comportan los modelos

Aquí vive todo lo que gobierna a un LLM dentro de regulabank: principios que no se negocian, prompts versionados,
el registro de herramientas que puede usar y la tabla de riesgo que decide cuándo entra una persona. El código los
lee de aquí; nunca hay un prompt escrito dentro de un `.py`.

| Archivo | Qué fija |
|---|---|
| `principles.md` | las diez reglas invariantes: qué puede y qué no puede hacer un modelo en este sistema |
| `style.md` | cómo habla el asistente: idioma, formato de cita, abstención, tono |
| `tools.md` | registro de herramientas de solo lectura, con esquema; el prompt las lista desde aquí |
| `risk.md` | triage `auto` / `notify` / `approve`: qué casos pausan para una persona |
| `prompts/answer.md` | nodo `answer`: redacta afirmaciones con cita, versión `p0` |
| `prompts/judge.md` | nodo `judge_evidence`: califica si la evidencia responde |
| `prompts/conflict.md` | nodo `judge` del grafo de conflictos: política ↔ norma |

## Reglas de este directorio

- **Cada prompt lleva `version` en su cabecera** y el ledger guarda esa versión con cada llamada. Cambiar el texto
  sin subir la versión está prohibido: invalidaría la comparación contra el golden.
- **Un cambio de prompt es un experimento:** se mide contra el golden reservado antes y después (`docs/10-evaluation.md`);
  entra solo si mejora sin empeorar otro escenario. El resultado se anota al pie del prompt.
- **Los prompts se escriben en español** (es el idioma del corpus y de los usuarios); los nombres de campos de la
  salida estructurada van en inglés, iguales a `backend/regulabank/api/contracts.py`.
- **Nada de ejemplos con datos reales de un banco.** Los ejemplos salen del corpus público o de las políticas
  sintéticas.
- **El código carga estos archivos tal cual** (`regulabank.agents.charter.load("answer")`), con el registro de
  herramientas renderizado desde `tools.md` y las reglas de riesgo desde `backend/seeds/risk_rules.csv`.
