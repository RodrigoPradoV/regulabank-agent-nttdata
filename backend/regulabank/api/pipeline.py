"""El flujo etapa por etapa, como dato: entrada, salida, transformers, parametros y cifras reales si existen.

Las cifras salen de los manifiestos del release (`data/releases/<id>/manifest.json`, `graph_manifest.json`); si no
existen, la etapa queda `pending`. Las definiciones (que entra, que sale, que modelo) viven aqui, no en el frontend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from regulabank.shared import config

Status = Literal["done", "partial", "pending"]


class Model(BaseModel):
    name: str                       # id de Hugging Face o del proveedor
    role: str                       # que hace en la etapa
    family: str                     # regex | gazetteer | ner | embedding | nli | llm | reranker
    size: str                       # 300M, large, api
    runs_on: str                    # cpu | mps | gpu | api
    status: Literal["active", "optional", "planned", "rejected"]
    why: str                        # motivo medido o decision


class Param(BaseModel):
    name: str
    value: str
    source: str                     # de donde sale el valor


class Stage(BaseModel):
    id: str
    area: Literal["corpus", "graph", "search", "agents"]
    label: str
    summary: str
    input_title: str
    input: list[str]
    output_title: str
    output: list[str]
    models: list[Model] = Field(default_factory=list)
    params: list[Param] = Field(default_factory=list)
    counts: dict[str, int | float | str] = Field(default_factory=dict)
    status: Status = "pending"
    doc: str                        # archivo de docs/ que lo define
    code: str                       # modulo que lo implementa


class Pipeline(BaseModel):
    release_id: str
    stages: list[Stage]


def _manifest(settings: config.Settings, name: str) -> dict:
    p = Path("data/releases") / settings.release_id / name
    if not p.exists():
        p = Path("data/releases/r0001") / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def build(settings: config.Settings) -> Pipeline:
    m = _manifest(settings, "manifest.json")
    g = _manifest(settings, "graph_manifest.json")
    counts_m = m.get("counts", {})
    counts_g = g.get("counts", {})

    def st(done: bool, partial: bool = False) -> Status:
        return "done" if done else ("partial" if partial else "pending")

    stages = [
        Stage(
            id="sources", area="corpus", label="Fuentes", summary="Qué documentos entran y con qué metadatos.",
            input_title="Lista de normas a mano", input=["seeds/norms.csv: id, número, emisor, publicación, vigencia, estado, URL", "seeds/synthetic/*.md: políticas internas y circulares sintéticas con los casos D-1 a D-6"],
            output_title="Catálogo normativo", output=["norms.parquet: una fila por documento, sha256 del original", "bronze/: el PDF o Markdown tal cual se bajó, nunca se modifica"],
            models=[Model(name="httpx", role="descarga con pausa de 5 s y freno al primer 403", family="regex", size="n/a", runs_on="cpu", status="active", why="sin navegador; portales del Estado")],
            params=[Param(name="corpus mínimo", value="25 documentos", source="SOW, componente 1"), Param(name="pausa entre peticiones", value="5 s", source="canon, baneo de IP en un sitio chico")],
            counts={"norms": counts_m.get("norms", 0)}, status=st(counts_m.get("norms", 0) >= 25, counts_m.get("norms", 0) > 0),
            doc="docs/02-corpus.md", code="backend/regulabank/corpus/{norms,capture}.py",
        ),
        Stage(
            id="extract", area="corpus", label="Ingesta", summary="Del PDF al texto por página, con offsets estables.",
            input_title="Originales en bronze", input=["PDF nativo o escaneado", "Markdown de políticas sintéticas"],
            output_title="Páginas (silver)", output=["pages.parquet por documento: page, text", "el texto no se toca después: las citas se verifican contra él"],
            models=[Model(name="pymupdf", role="texto por página con posición", family="regex", size="n/a", runs_on="cpu", status="active", why="rápido y determinista"), Model(name="tesseract", role="OCR solo si la página es imagen", family="regex", size="n/a", runs_on="cpu", status="optional", why="normas antiguas del Peruano escaneadas; OCR no se cita sin revisión")],
            params=[Param(name="gate", value="título, cuerpo, número de norma, ≥ 1 artículo, fecha", source="docs/02-corpus.md")],
            counts={"documents": counts_m.get("documents", counts_m.get("norms", 0)), "pages": counts_m.get("pages", 0)}, status=st(counts_m.get("pages", 0) > 0),
            doc="docs/02-corpus.md", code="backend/regulabank/corpus/extract.py",
        ),
        Stage(
            id="chunks", area="corpus", label="Chunks", summary="Unidad = artículo. Estructura por regex, sin solape, ids por contenido.",
            input_title="Páginas", input=["texto por página", "catálogo con vigencia por documento"],
            output_title="chunks.parquet", output=["artículo → chunk (los largos se parten por numeral)", "norm_id, article_id, version_id, valid_from/to, page_start/end, start/end, citation", "text == article_text[start:end]; fingerprint del conjunto"],
            models=[Model(name="regex de estructura", role="TÍTULO > CAPÍTULO > Artículo > numeral > literal", family="regex", size="n/a", runs_on="cpu", status="active", why="los encabezados legales son formulaicos; recall ≥ 0,98 esperado"), Model(name="segment-any-text sat-3l-sm", role="oraciones para citas cortas", family="ner", size="3 capas", runs_on="cpu", status="planned", why="52/60 fronteras vs 30 de regex en otro corpus; después del MVP")],
            params=[Param(name="cap de chunk", value=str(m.get("params", {}).get("chunk_cap_chars", "p95 del largo de artículos")), source="percentil 95 medido en este corpus, no un número fijo"), Param(name="pieza mínima", value="0,5 × objetivo", source="docs/03-chunking.md")],
            counts={"articles": counts_m.get("articles", 0), "chunks": counts_m.get("chunks", 0)}, status=st(counts_m.get("chunks", 0) > 0),
            doc="docs/03-chunking.md", code="backend/regulabank/corpus/{parse,chunks}.py",
        ),
        Stage(
            id="entities", area="graph", label="Entidades", summary="Lo formulaico por regex, lo abierto con GLiNER2. Grafo lens.",
            input_title="Chunks", input=["texto de cada chunk", "seeds/catalog.csv: reguladores, tipos de institución, riesgos, productos"],
            output_title="mentions.parquet + entities.parquet", output=["mención con start/end verificados y valor estructurado ({n: 15, unit: business_day})", "entidad canónica por tipo y clave; entra con ≥ 2 chunks"],
            models=[
                Model(name="regex", role="norm_ref, article_ref, deadline, amount, percentage, defined_term", family="regex", size="n/a", runs_on="cpu", status="active", why="forma fija: precisión casi perfecta; da las aristas REFERS_TO y los valores que comparan reglas"),
                Model(name="gazetteer", role="regulator, institution_type, risk, product", family="gazetteer", size="n/a", runs_on="cpu", status="active", why="vocabulario cerrado del dominio"),
                Model(name="fastino/gliner2-large-v1", role="role, sanction, report, obligation (zero-shot, etiquetas propias)", family="ner", size="large", runs_on="mps", status="optional", why="umbral 0,3 al extraer, corte después; en otro corpus 51 % → 99 % de precisión tras curar por entidad"),
                Model(name="mrm8488/bert-spanish-cased-finetuned-ner (BETO)", role="voto PER/ORG/LOC", family="ner", size="base", runs_on="cpu", status="rejected", why="decisión 2026-10-17: los tipos útiles aquí no son PER/ORG/LOC; el voto no corroboraba en otro corpus"),
            ],
            params=[Param(name="score GLiNER2", value="≥ 0,5 o 2 votos", source="provisional, calibrar con 200 chunks etiquetados"), Param(name="entidad entra", value="n_chunks ≥ 2 (o tipo norm_ref/article_ref/defined_term)", source="docs/04-entities.md")],
            counts={"mentions": counts_g.get("mentions", 0), "entities": counts_g.get("entities", 0)}, status=st(counts_g.get("entities", 0) > 0),
            doc="docs/04-entities.md", code="backend/regulabank/graphs/{entities,aggregate}.py",
        ),
        Stage(
            id="embed", area="graph", label="Embeddings", summary="Un vector por chunk más índice léxico; el embedding manda, lo demás vota.",
            input_title="Chunks con encabezado", input=["«{norma}, art. {n} | texto» (el encabezado va al vector, no a la cita)"],
            output_title="LanceDB", output=["tabla chunks: columnas del parquet + vector", "índice FTS en español (BM25) sobre text"],
            models=[
                Model(name="google/embeddinggemma-300m", role="embedding principal", family="embedding", size="300M, 768 d", runs_on="mps", status="active", why="nDCG@8 0,718 vs bge-m3 0,622 y Qwen3-0.6B 0,585 en un corpus en español de 30 mil chunks; 60-85 ms por consulta en CPU"),
                Model(name="intfloat/multilingual-e5-small", role="respaldo si gemma no está disponible", family="embedding", size="118M, 384 d", runs_on="cpu", status="optional", why="descarga sin puerta; se anota en el manifiesto cuál se usó"),
                Model(name="BM25 (FTS de LanceDB)", role="votante léxico débil (0,3)", family="regex", size="n/a", runs_on="cpu", status="active", why="números de artículo y siglas son tokens exactos; como igual al denso bajó nDCG 0,72 → 0,53"),
                Model(name="BAAI/bge-reranker-v2-m3", role="reordenar los 30 primeros", family="reranker", size="568M", runs_on="cpu", status="optional", why="+0,06 nDCG sobre 300 en otro corpus; 2-4 s; medir aquí"),
            ],
            params=[Param(name="prefijo doc", value="title: {norma}, art. {n} | text: ", source="docs/07-embeddings.md"), Param(name="prefijo query", value="task: search result | query: ", source="docs/07-embeddings.md")],
            counts={"vectors": counts_g.get("vectors", 0), "model": g.get("embed_model", "pendiente")}, status=st(counts_g.get("vectors", 0) > 0),
            doc="docs/07-embeddings.md", code="backend/regulabank/graphs/embed.py",
        ),
        Stage(
            id="graph", area="graph", label="Grafo", summary="Cuatro capas en un grafo: focus, horizon, lens y bridge. PageRank en memoria.",
            input_title="Chunks, entidades, catálogo", input=["prev/next y jerarquía de cada chunk", "referencias resueltas por regex", "vectores para kNN", "modifica / deroga / sustituye desde el catálogo"],
            output_title="edges.parquet → FalkorDB", output=["NEXT 0,5 · PARENT 1,0 · REFERS_TO 1,0 · SHARES_ENTITY idf · SIMILAR coseno · MENTIONS idf", "MODIFIES / REPEALS / REPLACES entre normas y artículos", "matriz scipy para PageRank personalizado (alpha 0,5, 30 iteraciones)"],
            models=[
                Model(name="kNN por embedding", role="SIMILAR entre normas distintas, k=10", family="embedding", size="n/a", runs_on="cpu", status="active", why="rescate semántico que el regex no ve"),
                Model(name="PageRank personalizado (HippoRAG 2)", role="multi salto desde entidades y mejores chunks", family="regex", size="n/a", runs_on="cpu", status="active", why="42 ms sobre 80 mil nodos en otro corpus; semilla = entidades (idf) + top 10 (1/rango)"),
                Model(name="DISRPT (disrpt_sft_qwen3)", role="relación discursiva entre chunks vecinos", family="nli", size="qwen3", runs_on="gpu", status="rejected", why="decisión 2026-10-17: solo confiable con conector explícito y la adyacencia ya está en NEXT"),
                Model(name="ARI (ArgumentMining-MultiLD)", role="apoya / ataca entre chunks", family="nli", size="xlm-r large", runs_on="gpu", status="rejected", why="27 «ataca» en 601 mil pares en otro corpus; las normas obligan, no argumentan"),
            ],
            params=[Param(name="pesos de arista", value="seeds/params.toml [ppr.edge_weights]", source="docs/06-graphs.md, cada uno con motivo"), Param(name="FalkorDB", value="v4.22.0, puerto 6381", source="la 6.x entra en pánico con tildes en el slow_log")],
            counts={"edges": counts_g.get("edges", 0), "nodes": counts_g.get("nodes", 0)}, status=st(counts_g.get("edges", 0) > 0),
            doc="docs/06-graphs.md", code="backend/regulabank/graphs/{edges,ppr,load}.py",
        ),
        Stage(
            id="conflicts", area="agents", label="Conflictos", summary="Política ↔ norma: reglas sobre valores, NLI en lo demás, persona confirma.",
            input_title="Pares candidatos", input=["coseno + léxico + entidad compartida (percentiles combinados)", "valores estructurados de ambos lados cuando existen (plazo, monto, %)"],
            output_title="Hallazgos con dos citas", output=["contradiction · outdated · repealed_reference · future_validity", "cada uno con method, score, evidencia literal y estado (pending_human → confirmed | dismissed)"],
            models=[
                Model(name="reglas sobre valores", role="20 días > 15 días → contradiction; 12 % > 10 % → contradiction", family="regex", size="n/a", runs_on="cpu", status="active", why="determinista y explicable; cubre D-1, D-3, D-6"),
                Model(name="joeddav/xlm-roberta-large-xnli", role="entailment / neutral / contradiction (premisa = norma, hipótesis = política)", family="nli", size="xlm-r large", runs_on="mps", status="active", why="decisión 2026-10-17: un solo modelo de relación entre textos; RoBERTa large NLI con español"),
                Model(name="juez LLM", role="solo el residuo; propone, no aplica", family="llm", size="api", runs_on="api", status="active", why="charter/prompts/conflict.md"),
            ],
            params=[Param(name="pares por chunk de política", value="K=30, nunca dentro de la misma norma", source="docs/05-relations.md"), Param(name="meta SOW", value="≥ 5 de 6 casos, ≤ 1 falso positivo", source="SOW 4.4")],
            counts={"pairs": counts_g.get("pairs", 0), "findings": counts_g.get("findings", 0)}, status="pending",
            doc="docs/05-relations.md", code="backend/regulabank/graphs/conflicts.py (pendiente)",
        ),
        Stage(
            id="retrieve", area="search", label="Recuperación", summary="Denso + BM25 débil + PageRank, vigencia al final, 8 chunks con cita.",
            input_title="Pregunta + as_of", input=["speller contra el vocabulario del corpus", "escenario y normas nombradas por regex", "entidades ancladas por n-gramas"],
            output_title="Top 8 con traza", output=["Hit: chunk, cita, quote, vigencia, historia, aristas", "versiones no vigentes a as_of pasan a history, nunca desaparecen"],
            models=[Model(name="RRF ponderada", role="denso 1,0 · bm25 0,3 · entidades 0,3 · ppr 0,3", family="regex", size="n/a", runs_on="cpu", status="active", why="«la vía más débil arrastra al resto»: pesos, no filtros")],
            params=[Param(name="CAND_K / FUSED_K / TOP_K", value="50 / 100 / 8", source="docs/08-retrieval.md"), Param(name="abstención", value="media de los 6 mejores ≥ percentil 5 de positivos", source="calibrar en el golden")],
            counts={}, status="pending", doc="docs/08-retrieval.md", code="backend/regulabank/search/ (pendiente)",
        ),
        Stage(
            id="answer", area="agents", label="Respuesta", summary="El modelo redacta con citas; el código verifica; la persona entra en lo riesgoso.",
            input_title="Top 8 + historia", input=["evidencia congelada: chunk_id, cita, texto, vigencia", "diff entre la versión citada y la anterior (código)"],
            output_title="Answer verificada", output=["claims: una afirmación = una cita literal (quote in text, chunk_id in seen)", "risk auto | notify | approve → interrupt", "ledger: modelo, prompt_version, seen, faltas, costo, latencia, minutos ahorrados"],
            models=[
                Model(name="OpenAI (gpt-4.1 / gpt-5)", role="redactor con salida estructurada", family="llm", size="api", runs_on="api", status="active", why="clave personal con tope por corrida; una llamada de prueba leyendo usage y finish_reason"),
                Model(name="FakeProvider", role="guion determinista para construir y probar sin gastar", family="llm", size="n/a", runs_on="cpu", status="active", why="todo el flujo se prueba con proveedor falso"),
            ],
            params=[Param(name="MAX_FIXES", value="2", source="charter/principles.md"), Param(name="prompt", value="charter/prompts/answer.md p0", source="versión en el ledger")],
            counts={}, status="partial", doc="docs/09-agents.md", code="backend/regulabank/agents/ (mock en api/mock.py)",
        ),
    ]
    return Pipeline(release_id=m.get("release_id", settings.release_id), stages=stages)
