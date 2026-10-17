"""Parser de estructura por reglas (docs/03-chunking.md): titulos, capitulos, articulos, numerales, literales,
disposiciones y anexos de normas peruanas; secciones numeradas de politicas internas en Markdown.

Produce unidades (la unidad citable: articulo, seccion de politica, numeral de primer nivel bajo un capitulo,
disposicion ordinal o anexo) como rangos [start, end) sobre el texto del documento. El texto nunca se altera:
toda unidad cumple text == doc_text[start:end].
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from regulabank.corpus.extract import page_of

ORD_M = (
    r"(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|S[ée]ptimo|Octavo|Noveno|D[ée]cimo|Und[ée]cimo|"
    r"Duod[ée]cimo|[ÚU]nico)"
)
ORD_F = (
    r"(?:(?:D[ée]cim[ao]|Vig[ée]sim[ao]|Trig[ée]sim[ao])(?:[ \t]+(?:Primera|Segunda|Tercera|Cuarta|Quinta|"
    r"Sexta|S[ée]ptima|Octava|Novena))?|Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|S[ée]ptima|Octava|"
    r"Novena|[ÚU]nica)"
)

RX_TITLE = re.compile(r"^[ \t]*T[ÍI]TULO[ \t]+(?P<no>PRELIMINAR|[IVXLC]+|\d+)\b", re.M)
RX_CHAPTER = re.compile(r"^[ \t]*(?P<word>(?:SUB)?CAP[ÍI]TULO)[ \t]+(?P<no>[IVXLCl]+|\d+|[ÚU]NICO)\b", re.M)
RX_ARTICLE = re.compile(
    r"^[ \t]*(?P<word>Art[íi]culo|Art\.)[ \t]*"
    r"(?P<no>\d+(?:[ \t]*-[ \t]*[A-Z](?![a-záéíóúA-Z]))?|" + ORD_M + r"\b)"
    r"(?P<deg>[ \t]*[°º])?(?P<sep>[ \t]*(?:\.-|\.|-|:))?",
    re.M,
)
RX_NUMERAL_UNIT = re.compile(r"^[ \t]*(?P<n>\d{1,3})\.[ \t]+(?P<title>[A-ZÁÉÍÓÚÑ][^\n]*)$", re.M)
RX_PROVISIONS = re.compile(
    r"^[ \t]*DISPOSICI[ÓO]N(?:ES)?[ \t]+(?P<words>(?:FINAL|TRANSITORIA|COMPLEMENTARIA|DEROGATORIA|"
    r"MODIFICATORIA)[^\n]*)$",
    re.M,
)
RX_PROV_ITEM = re.compile(r"^[ \t]*(?P<no>" + ORD_F + r")[ \t]*(?:\.?[ \t]*-|:)", re.M | re.I)
# Linea de portada de un cuerpo normativo (REGLAMENTO PARA ..., LEY GENERAL ...): reinicia todo el contexto.
RX_DOC_TITLE = re.compile(
    r"^[ \t]*(?:REGLAMENTO|NORMAS?|LEY|CIRCULAR|RESOLUCI[ÓO]N|TEXTO)\b[ \t]+[A-ZÁÉÍÓÚÑ0-9 ,.:;()/\-]{10,}[ \t]*$",
    re.M,
)
# Linea de indice: termina en puntos de guia y, opcionalmente, numero de pagina.
RX_TOC_LINE = re.compile(r"\.{4,}[ \t]*\d*[ \t]*$")
RX_ANNEX = re.compile(
    r"^[ \t]*(?:[\"“]Anexo|ANEXO)[ \t]+(?:N[°º\.]?[ \t]*)?(?P<no>\d+|[IVXL]+|[A-H])\b(?![ \t]*(?:de|del)\b)",
    re.M,
)
RX_ANNEX_NAMED = re.compile(r"^[ \t]*ANEXO[ \t]*[-–:][ \t]*(?P<name>[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,40})", re.M)

# Lineas internas de una unidad: candidatos de corte y etiquetas de ruta (nunca abren unidad por si solas).
RX_SUBNUM = re.compile(r"^[ \t]*(?P<label>\d+(?:\.\d+)+)\.?[ \t]+\S", re.M)
RX_NUM_LINE = re.compile(r"^[ \t]*(?P<label>\d{1,3})\.[ \t]+\S", re.M)
RX_LITERAL = re.compile(r"^[ \t]*(?P<label>[a-z]|[ivx]{1,5})[\)\.][ \t]+\S", re.M)
RX_MD_ITEM = re.compile(r"^[ \t]*[-*][ \t]+\S", re.M)

RX_MD_HEADING = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<text>.+?)[ \t]*#*[ \t]*$", re.M)
RX_MD_NUMBERED = re.compile(r"^(?P<no>\d+(?:\.\d+)*)\.?[ \t]+(?P<rest>.*)$")
# Normas sinteticas en Markdown: «## Artículo 8.- Clasificación» es un articulo, no una seccion de politica.
RX_MD_ARTICLE = re.compile(
    r"^(?:Art[íi]culo|Art\.)[ \t]*(?P<no>\d+(?:-[A-Z])?|" + ORD_M + r")[ \t]*[°º]?[ \t]*(?:\.-|\.|-|:)?[ \t]*(?P<rest>.*)$",
    re.I,
)
RX_MD_PROVISION = re.compile(r"^Disposici[óo]n(?:es)?[ \t]+(?P<rest>.+)$", re.I)
RX_MD_ANNEX = re.compile(r"^Anexo[ \t]+(?:N[°º.]?[ \t]*)?(?P<no>\d+|[IVXL]+|[A-H])\b[ \t]*(?:[.:-]+[ \t]*)?(?P<rest>.*)$", re.I)
RX_PARAGRAPH = re.compile(r"\n[ \t]*\n")

PROVISION_WORDS = ("FINAL", "TRANSITORIA", "COMPLEMENTARIA", "DEROGATORIA", "MODIFICATORIA")
ID_PREFIX = {"article": "art", "section": "sec", "numeral": "num", "provision": "disp", "annex": "anexo",
             "paragraph": "par"}
# Tipo de unidad del parser -> node_type del contrato (schema.NODE_TYPES). El numeral de primer nivel es una seccion.
NODE_TYPE = {"article": "article", "section": "section", "numeral": "section", "provision": "provision",
             "annex": "annex", "paragraph": "paragraph"}


@dataclass
class Cut:
    """Inicio de un numeral, literal o item dentro de una unidad (offset relativo al texto de la unidad)."""

    offset: int
    label: str
    kind: str  # numeral | literal | item


@dataclass
class Unit:
    """Unidad citable: rango exacto sobre el texto del documento."""

    kind: str  # article | section | numeral | provision | annex | paragraph
    no: str  # 12, 12-A, primero, 5.2, II.2, dcf-primera, 1
    label: str  # Articulo 12 / 5.2 Limites / Primera
    path: str  # TITULO II > CAPITULO I > Articulo 12
    start: int
    end: int
    text: str
    page_start: int
    page_end: int
    cuts: list[Cut] = field(default_factory=list)

    @property
    def id_suffix(self) -> str:
        return f"{ID_PREFIX[self.kind]}-{self.no}"

    @property
    def node_type(self) -> str:
        return NODE_TYPE[self.kind]


@dataclass
class ParsedDoc:
    text: str
    page_offsets: list[int]
    units: list[Unit]
    stats: dict
    fallback: bool = False  # True si no se detecto estructura y se corto por parrafos (confianza baja)


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[áà]", "a", s)
    s = re.sub(r"[éè]", "e", s)
    s = re.sub(r"[íì]", "i", s)
    s = re.sub(r"[óò]", "o", s)
    s = re.sub(r"[úùü]", "u", s)
    s = s.replace("ñ", "n")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "s"


def _line_end(text: str, pos: int) -> int:
    nl = text.find("\n", pos)
    return len(text) if nl < 0 else nl


def _cuts_for(text: str, markdown: bool) -> list[Cut]:
    cuts: dict[int, Cut] = {}
    for rx, kind in ((RX_SUBNUM, "numeral"), (RX_NUM_LINE, "numeral"), (RX_LITERAL, "literal")):
        for m in rx.finditer(text):
            if m.start() == 0:
                continue  # el propio encabezado de la unidad
            cuts.setdefault(m.start(), Cut(m.start(), m.group("label"), kind))
    if markdown:
        for m in RX_MD_ITEM.finditer(text):
            if m.start():
                cuts.setdefault(m.start(), Cut(m.start(), "", "item"))
    return [cuts[k] for k in sorted(cuts)]


def _close(
    units: list[Unit], text: str, offsets: list[int], open_unit: dict | None, end: int, markdown: bool
) -> None:
    """Cierra la unidad abierta en end (recortando espacio final) y la agrega si tiene cuerpo."""
    if open_unit is None:
        return
    start = open_unit["start"]
    while end > start and text[end - 1].isspace():
        end -= 1
    if end <= start:
        return
    body = text[start:end]
    if open_unit["kind"] == "annex" and "\n" not in body.strip():
        return  # anexo que solo es encabezado: su contenido ya esta en otras unidades
    units.append(
        Unit(
            kind=open_unit["kind"],
            no=open_unit["no"],
            label=open_unit["label"],
            path=open_unit["path"],
            start=start,
            end=end,
            text=body,
            page_start=page_of(offsets, start),
            page_end=page_of(offsets, end - 1),
            cuts=_cuts_for(body, markdown),
        )
    )


def _provision_abbr(words: str) -> str:
    found = [w[0].lower() for w in PROVISION_WORDS if w in words.upper()]
    return "d" + "".join(found) if found else "d"


def parse_norm(text: str, page_offsets: list[int]) -> ParsedDoc:
    """Norma peruana (ley, resolucion, circular) en texto plano de PDF."""
    boundaries: list[tuple[int, int, str, re.Match]] = []
    order = {"doc_title": 0, "title": 1, "chapter": 2, "provisions": 3, "annex": 4, "annex_named": 5,
             "article": 6, "numeral": 7, "prov_item": 8}
    for kind, rx in (
        ("doc_title", RX_DOC_TITLE),
        ("title", RX_TITLE),
        ("chapter", RX_CHAPTER),
        ("provisions", RX_PROVISIONS),
        ("annex", RX_ANNEX),
        ("annex_named", RX_ANNEX_NAMED),
        ("article", RX_ARTICLE),
        ("numeral", RX_NUMERAL_UNIT),
        ("prov_item", RX_PROV_ITEM),
    ):
        for m in rx.finditer(text):
            if RX_TOC_LINE.search(text[m.start():_line_end(text, m.start())]):
                continue  # linea de indice con puntos de guia
            boundaries.append((m.start(), order[kind], kind, m))
    boundaries.sort(key=lambda b: (b[0], b[1]))

    units: list[Unit] = []
    ctx = {"title": None, "chapter": None, "provisions": None, "annex": None}
    open_unit: dict | None = None
    seen_articles: set[str] = set()
    numeral_seq: dict[str, int] = {}
    stats = {"article_headers": 0, "article_duplicates": 0, "articles_in_annex": 0,
             "numeral_candidates": 0, "numeral_rejected": 0, "prov_items_rejected": 0}
    last_pos = -1

    def context_path() -> list[str]:
        parts = []
        if ctx["annex"]:
            parts.append(f"ANEXO {ctx['annex']}")
        if ctx["title"]:
            parts.append(f"TÍTULO {ctx['title']}")
        if ctx["chapter"]:
            parts.append(ctx["chapter"])
        if ctx["provisions"]:
            parts.append(ctx["provisions"])
        return parts

    def container_key() -> str:
        return "|".join(str(ctx[k]) for k in ("annex", "title", "chapter", "provisions"))

    for pos, _, kind, m in boundaries:
        if pos == last_pos:
            continue  # dos regex sobre la misma linea: gana el primero por orden
        if kind == "doc_title":
            _close(units, text, page_offsets, open_unit, pos, False)
            open_unit = None
            ctx.update(title=None, chapter=None, provisions=None, annex=None)
            last_pos = pos
        elif kind == "title":
            _close(units, text, page_offsets, open_unit, pos, False)
            open_unit = None
            ctx.update(title=m.group("no").upper(), chapter=None, provisions=None, annex=None)
            last_pos = pos
        elif kind == "chapter":
            _close(units, text, page_offsets, open_unit, pos, False)
            open_unit = None
            raw = m.group("no")
            no = raw.upper().replace("L", "I") if re.fullmatch(r"[IVXl]+", raw) else raw.upper()
            word = m.group("word").upper().replace("CAPITULO", "CAPÍTULO")
            ctx.update(chapter=f"{word} {no}", provisions=None)
            last_pos = pos
        elif kind == "provisions":
            _close(units, text, page_offsets, open_unit, pos, False)
            open_unit = None
            label = _collapse(text[pos:_line_end(text, pos)])
            label = re.sub(r"[\s.]+\d*$", "", label)  # puntos de indice y numero de pagina
            ctx.update(provisions=label.upper(), chapter=None)
            last_pos = pos
        elif kind in ("annex", "annex_named"):
            _close(units, text, page_offsets, open_unit, pos, False)
            no = m.group("no").upper() if kind == "annex" else _slug(m.group("name"))
            ctx.update(annex=no, title=None, chapter=None, provisions=None)
            numeral_seq.pop(container_key(), None)
            open_unit = {"kind": "annex", "no": no.lower() if kind == "annex_named" else no,
                         "label": f"ANEXO {no}", "path": " > ".join(context_path()), "start": pos}
            last_pos = pos
        elif kind == "article":
            stats["article_headers"] += 1
            word, deg, sep = m.group("word"), m.group("deg"), m.group("sep")
            if sep is None or (word == "Art." and not (sep.strip() == ".-" or deg)):
                continue
            no = re.sub(r"[ \t]", "", m.group("no"))
            if not no[0].isdigit():
                no = no.lower()
            if ctx["annex"] and open_unit is not None:
                stats["articles_in_annex"] += 1
                continue
            if no in seen_articles:
                stats["article_duplicates"] += 1
                continue
            seen_articles.add(no)
            _close(units, text, page_offsets, open_unit, pos, False)
            label = f"Artículo {m.group('no').strip().title() if not no[0].isdigit() else no}"
            open_unit = {"kind": "article", "no": no, "label": label,
                         "path": " > ".join(context_path() + [label]), "start": pos}
            last_pos = pos
        elif kind == "numeral":
            stats["numeral_candidates"] += 1
            if open_unit is not None and open_unit["kind"] in ("article", "provision", "section"):
                continue  # numeral interno de un articulo
            if not (ctx["chapter"] or ctx["annex"]):
                continue
            n = int(m.group("n"))
            title = m.group("title").rstrip()
            key = container_key()
            expected = numeral_seq.get(key, 0) + 1
            if n != expected or title.endswith((".", ";", ",", ":")):
                stats["numeral_rejected"] += 1
                continue
            numeral_seq[key] = n
            _close(units, text, page_offsets, open_unit, pos, False)
            chapter_no = (ctx["chapter"] or "").split(" ")[-1]
            prefix = (f"A{ctx['annex']}." if ctx["annex"] else "") + (f"{chapter_no}." if chapter_no else "")
            label = _collapse(f"{n}. {title}")[:60]
            open_unit = {"kind": "numeral", "no": f"{prefix}{n}", "label": label,
                         "path": " > ".join(context_path() + [label]), "start": pos}
            last_pos = pos
        elif kind == "prov_item":
            if not ctx["provisions"] or (open_unit is not None and open_unit["kind"] == "article"):
                stats["prov_items_rejected"] += 1
                continue
            _close(units, text, page_offsets, open_unit, pos, False)
            ordinal = _collapse(m.group("no")).lower()
            label = ordinal.title()
            open_unit = {"kind": "provision", "no": f"{_provision_abbr(ctx['provisions'])}-{_slug(ordinal)}",
                         "label": label, "path": " > ".join(context_path() + [label]), "start": pos}
            last_pos = pos
    _close(units, text, page_offsets, open_unit, len(text), False)
    return ParsedDoc(text, page_offsets, units, _finish_stats(stats, units, text))


def parse_markdown(text: str, page_offsets: list[int]) -> ParsedDoc:
    """Politica interna en Markdown: cada encabezado numerado (## 5.2 Titulo) es una seccion = articulo."""
    units: list[Unit] = []
    stack: list[tuple[int, str]] = []
    open_unit: dict | None = None
    stats = {"headings": 0, "unnumbered_sections": 0}
    for m in RX_MD_HEADING.finditer(text):
        level = len(m.group("hashes"))
        heading = _collapse(m.group("text"))
        stats["headings"] += 1
        _close(units, text, page_offsets, open_unit, m.start(), True)
        open_unit = None
        while stack and stack[-1][0] >= level:
            stack.pop()
        if level == 1:
            stack.append((1, heading))
            continue
        kind, no, label = _md_heading_unit(heading, stats)
        path = " > ".join([s[1] for s in stack] + [label])
        stack.append((level, label))
        open_unit = {"kind": kind, "no": no, "label": label, "path": path, "start": m.start()}
    _close(units, text, page_offsets, open_unit, len(text), True)
    return ParsedDoc(text, page_offsets, units, _finish_stats(stats, units, text))


def _md_heading_unit(heading: str, stats: dict) -> tuple[str, str, str]:
    """(kind, no, label) de un encabezado Markdown: articulo, disposicion, anexo o seccion numerada."""
    art = RX_MD_ARTICLE.match(heading)
    if art:
        no = art.group("no")
        no = no if no[0].isdigit() else no.lower()
        return "article", no, f"Artículo {no if no[0].isdigit() else no.title()}"
    annex = RX_MD_ANNEX.match(heading)
    if annex:
        return "annex", annex.group("no").upper(), f"ANEXO {annex.group('no').upper()}"
    prov = RX_MD_PROVISION.match(heading)
    if prov:
        return "provision", f"d-{_slug(prov.group('rest'))}", heading
    num = RX_MD_NUMBERED.match(heading)
    if num:
        return "section", num.group("no"), f"{num.group('no')} {_collapse(num.group('rest'))}"
    stats["unnumbered_sections"] += 1
    return "section", _slug(heading), heading


def parse_paragraphs(text: str, page_offsets: list[int]) -> ParsedDoc:
    """Repuesto cuando ningun parser detecta estructura: cada parrafo (separado por linea en blanco) es una unidad.

    Las filas salen con confianza baja y review_required (docs/03-chunking.md): sirven para buscar, no para citar
    un articulo.
    """
    units: list[Unit] = []
    pos = 0
    n = 0
    for m in list(RX_PARAGRAPH.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        body = text[pos:end]
        lead = len(body) - len(body.lstrip())
        start = pos + lead
        if body.strip():
            n += 1
            label = f"Párrafo {n}"
            unit = {"kind": "paragraph", "no": str(n), "label": label, "path": label, "start": start}
            _close(units, text, page_offsets, unit, end, False)
        pos = m.end() if m else end
    stats = {"paragraphs": n}
    return ParsedDoc(text, page_offsets, units, _finish_stats(stats, units, text), fallback=True)


def _finish_stats(stats: dict, units: list[Unit], text: str) -> dict:
    by_kind: dict[str, int] = {}
    for u in units:
        by_kind[u.kind] = by_kind.get(u.kind, 0) + 1
    covered = sum(u.end - u.start for u in units)
    stripped = len(text.strip())
    stats.update(
        units=len(units),
        by_kind=by_kind,
        covered_chars=covered,
        uncovered_chars=max(stripped - covered, 0),
        coverage=round(covered / stripped, 4) if stripped else 0.0,
    )
    return stats


def parse_pages(pages: list[str], suffix: str) -> ParsedDoc:
    """Elige el parser por extension de la fuente (.md es politica; el resto, norma en texto plano)."""
    from regulabank.corpus.extract import join_pages

    text, offsets = join_pages(pages)
    if suffix.lower() in (".md", ".markdown"):
        parsed = parse_markdown(text, offsets)
    else:
        parsed = parse_norm(text, offsets)
    if not parsed.units:
        parsed = parse_paragraphs(text, offsets)
    return parsed
