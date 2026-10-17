"""Genera `chunks_fixture.parquet`: 3 normas ficticias x 6 articulos con texto legal verosimil (esquema CHUNKS).

Sirve para probar la etapa graphs sin el parser real. Contiene referencias normativas, plazos, montos,
porcentajes, terminos definidos, reguladores, roles, listas y rangos de articulos. El articulo 6 de la politica
va partido en dos chunks (prueba NEXT por orden de filas).

    python tests/fixtures/make_chunks_fixture.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regulabank.shared import schema  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "chunks_fixture.parquet"

NORMS = {
    "pe-sbs-res-11356-2008": {
        "short": "Res. SBS 11356-2008", "title": "Reglamento para la Evaluación y Clasificación del Deudor",
        "kind": "sbs_resolution", "issuer": "SBS", "published": "2008-11-19", "valid_from": "2009-07-01",
        "status": "in_force", "prefix": "art", "node_type": "article",
        "articles": {
            "1": ("TÍTULO I > Artículo 1", [
                "La presente norma es aplicable a las empresas del sistema financiero comprendidas en los literales "
                "A y B del artículo 16 de la Ley General del Sistema Financiero y del Sistema de Seguros y Orgánica "
                "de la Superintendencia de Banca y Seguros, Ley N.° 26702, en adelante la Ley General, así como a "
                "las cajas municipales y las EDPYME. La Superintendencia podrá extender su alcance a las "
                "cooperativas de ahorro y crédito mediante norma de carácter general.",
            ]),
            "2": ("TÍTULO I > Artículo 2 > Definiciones", [
                "Para los efectos de la presente norma se entiende por:\n"
                "a) Deudor minorista: aquella persona natural o jurídica que cuenta con créditos de consumo, "
                "créditos a microempresas o créditos hipotecarios para vivienda.\n"
                "b) Deudor no minorista: aquella persona natural o jurídica que cuenta con créditos corporativos, "
                "a grandes empresas o a medianas empresas.\n"
                "c) Exposición equivalente a riesgo crediticio: el resultado de multiplicar los créditos indirectos "
                "por los factores de conversión crediticios.",
            ]),
            "3": ("TÍTULO II > Artículo 3", [
                "El deudor minorista se clasifica en función de los días de atraso en el pago. Se considera con "
                "problemas potenciales al deudor que registra atraso entre nueve (9) y treinta (30) días calendario; "
                "deficiente, entre treinta y uno (31) y sesenta (60) días calendario; dudoso, entre sesenta y uno "
                "(61) y ciento veinte (120) días calendario; y pérdida, más de ciento veinte (120) días calendario.",
            ]),
            "4": ("TÍTULO II > Artículo 4", [
                "Las empresas constituirán provisiones genéricas no menores al uno por ciento (1%) sobre los "
                "créditos de consumo clasificados en categoría normal, y del 0.7 % sobre los créditos hipotecarios "
                "para vivienda. En el caso de créditos corporativos la tasa será de 0,70 %. Las provisiones "
                "específicas por riesgo de crédito se calcularán conforme al Anexo I, y el Directorio aprobará la "
                "política de provisiones voluntarias.",
            ]),
            "5": ("TÍTULO III > Artículo 5", [
                "Las empresas remitirán a la Superintendencia el Reporte de Clasificación del Deudor dentro de los "
                "quince (15) días hábiles siguientes al cierre de cada mes, conforme al artículo 3 de la presente "
                "norma y al Anexo N.° 6. La información se presentará en soles; los créditos en moneda extranjera "
                "se convertirán al tipo de cambio contable publicado por la SBS.",
            ]),
            "6": ("TÍTULO III > Artículo 6", [
                "Los créditos clasificados en pérdida, íntegramente provisionados, podrán castigarse cuando el saldo "
                "sea menor a S/ 10 000 o su equivalente en dólares, previa comunicación al Directorio. Las "
                "operaciones por montos superiores a USD 10,000 requieren aprobación de la Gerencia General. La "
                "presente Resolución entra en vigencia a los doce (12) meses de su publicación y modifica el "
                "artículo 2 de la Resolución SBS N.° 808-2003. Los artículos 1 al 4 rigen desde su publicación.",
            ]),
        },
    },
    "pe-sbs-res-2660-2015": {
        "short": "Res. SBS 2660-2015", "title": "Reglamento de Gestión de Riesgos de LA/FT",
        "kind": "sbs_resolution", "issuer": "SBS", "published": "2015-05-18", "valid_from": "2015-07-01",
        "status": "in_force", "prefix": "art", "node_type": "article",
        "articles": {
            "1": ("TÍTULO I > Artículo 1", [
                "El presente Reglamento es de aplicación a las empresas señaladas en los artículos 16 y 17 de la "
                "Ley General, a las cooperativas de ahorro y crédito y a las empresas de seguros, en su calidad de "
                "sujetos obligados a informar a la Unidad de Inteligencia Financiera del Perú (UIF-Perú), conforme "
                "a la Ley N.° 27693.",
            ]),
            "2": ("TÍTULO I > Artículo 2 > Definiciones", [
                "Para efectos del presente Reglamento se entiende por Operación sospechosa: aquella operación "
                "inusual que, por su cuantía o características, no guarda relación con la actividad económica del "
                "cliente. Asimismo:\n"
                "a) Oficial de Cumplimiento: la persona natural designada por el Directorio como responsable de "
                "vigilar la adecuada implementación del sistema de prevención del LA/FT.\n"
                "b) Beneficiario final: la persona natural que efectivamente posee o controla a un cliente.\n"
                "c) Riesgos de LA/FT: la posibilidad de que la empresa sea utilizada para fines de lavado de "
                "activos y del financiamiento del terrorismo.",
            ]),
            "3": ("TÍTULO II > Artículo 3", [
                "El Directorio designa al Oficial de Cumplimiento, quien tiene rango de gerente y depende "
                "directamente del Directorio. La designación se comunica a la Superintendencia y a la UIF-Perú "
                "dentro de los quince (15) días hábiles de producida. El Oficial de Cumplimiento no puede ser el "
                "Gerente General ni el auditor interno. Las cajas municipales y las EDPYME pueden contar con un "
                "Oficial de Cumplimiento a dedicación no exclusiva, previa autorización de la SBS.",
            ]),
            "4": ("TÍTULO II > Artículo 4", [
                "Las empresas comunican a la UIF-Perú las operaciones sospechosas mediante el Reporte de "
                "Operaciones Sospechosas (ROS) en un plazo máximo de quince (15) días hábiles de detectada la "
                "operación. El Registro de Operaciones comprende las operaciones individuales por montos iguales o "
                "superiores a diez mil dólares americanos (USD 10,000) o su equivalente en moneda nacional, y las "
                "operaciones múltiples que en conjunto superen los cincuenta mil dólares (USD 50,000) en un mes "
                "calendario. El ROS no requiere aprobación del Directorio ni de la Gerencia General.",
            ]),
            "5": ("TÍTULO III > Artículo 5", [
                "El incumplimiento de las obligaciones previstas en los artículos 3 y 4 del presente Reglamento "
                "constituye infracción grave, sancionable con multa de hasta cien (100) UIT, conforme al Reglamento "
                "de Sanciones aprobado por Resolución SBS N.° 2755-2018. Tratándose de cooperativas, la multa no "
                "podrá exceder el diez por ciento (10%) del patrimonio efectivo. Las empresas del sistema "
                "financiero deben, además, remitir el informe anual del Oficial de Cumplimiento a la "
                "Superintendencia dentro de los treinta (30) días calendario siguientes al cierre del ejercicio.",
            ]),
            "6": ("TÍTULO III > Artículo 6", [
                "La presente Resolución entra en vigencia el 1 de julio de 2015 y deroga la Resolución SBS "
                "N.° 838-2008, con excepción de su artículo 10, que mantiene vigencia hasta el 31 de diciembre de "
                "2015. Las políticas internas de las empresas deberán adecuarse en un plazo de ciento veinte (120) "
                "días calendario, bajo supervisión de la Unidad de Riesgos y de Auditoría Interna.",
            ]),
        },
    },
    "pe-bank-pol-laft-2024": {
        "short": "Política LAFT 2024", "title": "Política de Prevención LA/FT 2024",
        "kind": "internal_policy", "issuer": "Banco", "published": "2024-01-15", "valid_from": "2024-01-15",
        "status": "in_force", "prefix": "sec", "node_type": "section",
        "articles": {
            "1": ("Política LAFT 2024 > 1 Objetivo", [
                "Esta política establece los lineamientos del Banco para la prevención del lavado de activos y del "
                "financiamiento del terrorismo, en cumplimiento de la Resolución SBS N.° 2660-2015 y de la "
                "Ley N.° 26702. Aplica a todas las unidades del Banco y a sus subsidiarias financieras.",
            ]),
            "2": ("Política LAFT 2024 > 2 Responsables", [
                "El Oficial de Cumplimiento reporta al Directorio y coordina con la Gerencia General, la Unidad de "
                "Riesgos y Auditoría Interna. El Directorio aprueba esta política y la revisa cada doce (12) meses, "
                "o antes si la SBS o la UIF-Perú emiten nuevas disposiciones.",
            ]),
            "3": ("Política LAFT 2024 > 3 Reporte de operaciones", [
                "El Oficial de Cumplimiento remite el Reporte de Operaciones Sospechosas a la UIF-Perú dentro de "
                "los veinte (20) días hábiles de detectada la operación, conforme al artículo 4 de la Resolución "
                "SBS N.° 2660-2015. Se registran las operaciones iguales o superiores a USD 10,000 o S/ 35 000, "
                "incluidas las transferencias de fondos y los depósitos a plazo.",
            ]),
            "4": ("Política LAFT 2024 > 4 Clasificación de clientes", [
                "Para efectos de esta política se entiende por Cliente de alto riesgo: aquel cliente cuya "
                "actividad, zona geográfica o producto presenta mayor exposición al riesgo de LA/FT. Los clientes "
                "que operan con tarjeta de crédito o crédito hipotecario por montos superiores a S/ 50 000 se "
                "revisan trimestralmente. El deudor minorista se clasifica conforme al artículo 2 de la "
                "Resolución SBS N.° 11356-2008.",
            ]),
            "5": ("Política LAFT 2024 > 5 Sanciones internas", [
                "El incumplimiento de esta política se sanciona con amonestación escrita, suspensión o despido, "
                "sin perjuicio de las multas que imponga la SBS conforme a la Circular N.° B-2200-2018 y al "
                "artículo 5 de la Resolución SBS N.° 2660-2015. La multa interna no excederá el cinco por ciento "
                "(5%) de la remuneración mensual del colaborador.",
            ]),
            "6": ("Política LAFT 2024 > 6 Capacitación", [
                "Todo el personal del Banco recibe capacitación anual en prevención de LA/FT. Los nuevos "
                "colaboradores reciben inducción dentro de los treinta (30) días calendario de su ingreso. La Unidad "
                "de Riesgos evalúa el riesgo operacional y el riesgo de crédito asociado a los productos nuevos "
                "antes de su lanzamiento.\n",
                "El programa de capacitación se aprueba por la Gerencia General y se reporta al Directorio. La "
                "Superintendencia puede solicitar las constancias de capacitación en cualquier momento, conforme a "
                "la Resolución SBS N.° 2660-2015 y al riesgo operacional identificado.",
            ]),
        },
    },
}


def chunk_id(norm_id: str, article_id: str, page_start: int, index: int) -> str:
    return "c_" + hashlib.sha1(f"{norm_id}:{article_id}:{page_start}:{index}".encode()).hexdigest()[:16]


def build_chunks() -> pa.Table:
    rows: list[dict] = []
    for norm_id, norm in NORMS.items():
        for idx, (no, (path, pieces)) in enumerate(norm["articles"].items()):
            article_id = f"{norm_id}#{norm['prefix']}-{no}"
            page = 1 + idx // 3
            label = "art." if norm["node_type"] == "article" else "sec."
            for i, piece in enumerate(pieces):
                rows.append({
                    "chunk_id": chunk_id(norm_id, article_id, page, i), "norm_id": norm_id,
                    "norm_short": norm["short"], "title": norm["title"], "issuer": norm["issuer"],
                    "jurisdiction": "PE", "norm_kind": norm["kind"], "status": norm["status"],
                    "published": norm["published"], "valid_from": norm["valid_from"], "valid_to": None,
                    "source_url": None, "source_path": f"tests/fixtures/{norm_id}.txt", "source_sha256": None,
                    "article_id": article_id, "article_no": no, "node_type": norm["node_type"],
                    "parent_path": path, "page_start": page, "page_end": page, "text": piece,
                    "citation": f"{norm['short']}, {label} {no}, p. {page}", "extraction_method": "regex",
                    "confidence": 1.0, "review_required": False,
                })
    return pa.Table.from_pylist(rows, schema=schema.CHUNKS)


def main() -> None:
    table = build_chunks()
    pq.write_table(table, FIXTURE_PATH)
    print(f"{FIXTURE_PATH}: {table.num_rows} chunks")


if __name__ == "__main__":
    main()
