"""Integridad de la entrada y de la salida, en codigo y sin llamar al modelo.

Entrada: si la pregunta trae groserias o insultos, intenta cambiar las instrucciones del asistente (inyeccion de prompt), no es texto legible
o es demasiado larga, NO se llama al modelo: no se gasta nada y se responde con un aviso. Salida: la respuesta no puede traer lenguaje ofensivo ni
filtrar las instrucciones internas. Las listas son cortas y a proposito: lo ambiguo lo decide el agente (se abstiene si no hay sustento).
"""

from __future__ import annotations

import re
import unicodedata

MAX_CHARS = 1000
MIN_LETTERS = 3

# Groserias e insultos frecuentes en espanol (con variantes peruanas). Se comparan palabras completas, sin tildes y sin ofuscacion («m1erd@»).
PROFANITY = {
    "mierda", "puta", "puto", "putas", "putos", "carajo", "cojudo", "cojuda", "huevon", "huevona", "conchatumadre", "ctm", "ptm", "hdp", "pendejo", "pendeja",
    "imbecil", "idiota", "estupido", "estupida", "maldito", "maldita", "joder", "jodete", "coño", "cono", "verga", "chucha", "cabron", "cabrona", "malparido",
    "gilipollas", "culiao", "pelotudo", "boludo", "mrd", "concha", "conchudo", "hijueputa", "gonorrea", "marica", "maricon", "zorra", "basura humana",
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard",
}
INJECTION = [
    r"ignor[ae]\w*\s+(todas?\s+)?(las\s+|tus\s+|mis\s+)?(instrucciones|reglas|indicaciones)",
    r"olvida\w*\s+(todo|lo anterior|tus instrucciones|las reglas)",
    r"(muestra|revela|dime|imprime|repite|escribe)\w*.{0,40}(system prompt|prompt del sistema|tus instrucciones|instrucciones internas|tu prompt)",
    r"\bact[uú]a como\b", r"\beres ahora\b", r"\bfinge (ser|que)\b", r"\bmodo (desarrollador|dios|sin restricciones)\b",
    r"ignore (all|any|the|your|previous)\b.{0,30}(instructions|rules)", r"\bsystem prompt\b", r"\bjailbreak\b", r"do anything now", r"\bdeveloper mode\b",
    r"reveal (your|the) (prompt|instructions)", r"\bpretend (to be|you are)\b",
]
LEAK = [r"eres un analista de cumplimiento", r"herramientas de solo lectura", r"tu primer paso es siempre", r"respeta el presupuesto de llamadas", r"plan_registrado"]

REFUSAL = {
    "profanity": "Respondo preguntas sobre las normas del corpus. Reformula tu pregunta sin lenguaje ofensivo y con gusto la reviso.",
    "injection": "Solo respondo preguntas sobre las normas del corpus y no puedo cambiar ni mostrar mis instrucciones. Haz una pregunta sobre una norma.",
    "unreadable": "No entendí la pregunta. Escríbela con palabras completas, por ejemplo: «¿Cuál es el plazo para reportar una operación sospechosa?».",
    "too_long": f"La pregunta es demasiado larga (máximo {MAX_CHARS} caracteres). Resúmela en una o dos frases.",
}
_LEET = str.maketrans({"1": "i", "3": "e", "0": "o", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("ñ", "n")


def _tokens(text: str) -> list[str]:
    plain = _norm(text)
    # sin cambiar los numeros reales: la version «leet» solo se usa para las palabras con letras
    words = re.findall(r"[a-z0-9@$!]+", plain)
    out = []
    for w in words:
        w2 = re.sub(r"(.)\1{2,}", r"\1", w.translate(_LEET)) if re.search(r"[a-z]", w) else w
        out.append(w2)
    return out


def has_profanity(text: str) -> bool:
    bad = {_norm(p) for p in PROFANITY if " " not in p}
    toks = _tokens(text)
    joined = " ".join(toks)
    return any(t in bad for t in toks) or "basura humana" in joined or any(p in joined for p in ("hijo de puta", "hijo de tu madre", "tu madre"))


def _wordlike(tok: str) -> bool:
    """Una palabra legible tiene una vocal y ninguna racha de 5 consonantes seguidas (asdkjh no, construccion si)."""
    return bool(re.search(r"[aeiou]", tok)) and not re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", tok)


def check_question(text: str) -> tuple[bool, str | None]:
    """(permitida, motivo) — motivo es la clave de REFUSAL cuando se bloquea."""
    t = (text or "").strip()
    letters = sum(c.isalpha() for c in t)
    if letters < MIN_LETTERS or (t and letters / len(t) < 0.45):
        return False, "unreadable"
    words = [w for w in re.findall(r"[a-z]{2,}", _norm(t))]
    if words and sum(_wordlike(w) for w in words) / len(words) < 0.5:
        return False, "unreadable"
    if len(t) > MAX_CHARS:
        return False, "too_long"
    low = _norm(t)
    if any(re.search(p, low) for p in INJECTION):
        return False, "injection"
    if has_profanity(t):
        return False, "profanity"
    return True, None


def check_answer(text: str) -> str | None:
    """Falla de la salida: lenguaje ofensivo o filtracion de las instrucciones internas; None si esta limpia."""
    low = _norm(text)
    if any(re.search(p, low) for p in LEAK):
        return "la respuesta filtra instrucciones internas"
    if has_profanity(text):
        return "la respuesta contiene lenguaje ofensivo"
    return None
