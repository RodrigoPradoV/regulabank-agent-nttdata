# Herramientas del modelo (registro único)

Todas son de **solo lectura sobre el release congelado**. Ninguna toca la red ni escribe. El error vuelve como dato
(`{"error": "..."}`), nunca como excepción. El prompt lista estas herramientas desde este archivo; no se declaran
dos veces.

| name | args | returns | para qué |
|---|---|---|---|
| `read_chunk` | `chunk_id: str` | `{chunk_id, text, citation, valid_from, valid_to, article_id}` | leer un chunk completo; lo agrega a `seen` |
| `neighbors` | `chunk_id: str` | `[{chunk_id, relation: NEXT|PARENT, citation}]` | contexto inmediato del artículo |
| `refers_to` | `chunk_id: str` | `[{article_id, citation, chunk_ids}]` | seguir una remisión («conforme al artículo 8») |
| `article_history` | `article_id: str` | `[{version_id, valid_from, valid_to, change_kind, changed_by}]` | ver versiones; el texto se lee con `read_chunk` |
| `policy_links` | `chunk_id: str` | `[{policy_chunk_id, relation, score, status}]` | políticas internas enlazadas a un artículo |
| `search` | `query: str, k: int = 5` | `[{chunk_id, citation, score}]` | búsqueda adicional acotada; máximo 2 por corrida |

Reglas:
- Tope de pasos por corrida: `MAX_STEPS = 8`. Al tope, el modelo debe responder con lo que tiene o abstenerse.
- `search` cuenta contra el presupuesto; `read_chunk` no.
- Cada herramienta tiene test sin modelo (entrada real, salida válida e inválida) y su uso queda contado en el
  ledger (qué herramientas usó, cuántas citas pasaron `verify`).
