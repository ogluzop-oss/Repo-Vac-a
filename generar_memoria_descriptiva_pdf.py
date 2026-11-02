#!/usr/bin/env python3
"""
Convierte Memoria_Descriptiva_Software.md a Memoria_Descriptiva_Software.pdf usando reportlab
(flujo de párrafos/tablas real — sin ningún renderizador Markdown/LaTeX de terceros, para evitar el
problema de maquetación ya detectado con herramientas externas).

Uso:
    python generar_memoria_descriptiva_pdf.py
"""

import os
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
ENTRADA = os.path.join(ROOT, "Memoria_Descriptiva_Software.md")
SALIDA = os.path.join(ROOT, "Memoria_Descriptiva_Software.pdf")

# ── Estilos ──────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()
ESTILOS = {
    "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Helvetica-Bold",
                              fontSize=18, spaceAfter=14, textColor=colors.HexColor("#0B2545")),
    "h2": ParagraphStyle("h2", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=13,
                          spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#0B2545")),
    "h3": ParagraphStyle("h3", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
                          spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#12395B")),
    "cuerpo": ParagraphStyle("cuerpo", parent=base["BodyText"], fontName="Helvetica", fontSize=10,
                              leading=14, spaceAfter=8, alignment=4),  # 4 = justificado
    "celda": ParagraphStyle("celda", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5,
                             leading=11),
    "celda_cab": ParagraphStyle("celda_cab", parent=base["BodyText"], fontName="Helvetica-Bold",
                                 fontSize=8.5, leading=11, textColor=colors.white),
    "nota_final": ParagraphStyle("nota_final", parent=base["BodyText"], fontName="Helvetica-Oblique",
                                  fontSize=9, leading=13, textColor=colors.HexColor("#555555")),
}


def escapar_xml(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_md(texto):
    """Convierte **negrita** y *cursiva* de Markdown a las etiquetas de reportlab, tras escapar
    XML — no pasa por ningún motor Markdown/LaTeX de terceros."""
    texto = escapar_xml(texto)
    texto = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    texto = re.sub(r"\*(.+?)\*", r"<i>\1</i>", texto)
    return texto


def parsear_tabla(lineas_tabla):
    filas = [l for l in lineas_tabla if not re.match(r"^\s*\|[\s:\-|]+\|\s*$", l)]
    datos = []
    for i, linea in enumerate(filas):
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        estilo = ESTILOS["celda_cab"] if i == 0 else ESTILOS["celda"]
        datos.append([Paragraph(inline_md(c), estilo) for c in celdas])
    return datos


def construir_story(md_texto):
    story = []
    lineas = md_texto.splitlines()
    i = 0
    parrafo_buf = []

    def flush_parrafo():
        if parrafo_buf:
            texto = " ".join(parrafo_buf).strip()
            if texto:
                estilo = ESTILOS["nota_final"] if texto.startswith("*") and texto.endswith("*") \
                    and not texto.startswith("**") else ESTILOS["cuerpo"]
                story.append(Paragraph(inline_md(texto), estilo))
            parrafo_buf.clear()

    while i < len(lineas):
        linea = lineas[i]
        stripped = linea.strip()

        if stripped == "":
            flush_parrafo()
            i += 1
            continue

        if stripped == "---":
            flush_parrafo()
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#B9C4CE")))
            story.append(Spacer(1, 10))
            i += 1
            continue

        if stripped.startswith("### "):
            flush_parrafo()
            story.append(Paragraph(inline_md(stripped[4:]), ESTILOS["h3"]))
            i += 1
            continue

        if stripped.startswith("## "):
            flush_parrafo()
            story.append(Paragraph(inline_md(stripped[3:]), ESTILOS["h2"]))
            i += 1
            continue

        if stripped.startswith("# "):
            flush_parrafo()
            story.append(Paragraph(inline_md(stripped[2:]), ESTILOS["titulo"]))
            i += 1
            continue

        if stripped.startswith("|"):
            flush_parrafo()
            bloque = []
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                bloque.append(lineas[i])
                i += 1
            datos = parsear_tabla(bloque)
            n_cols = len(datos[0]) if datos else 2
            ancho_total = (A4[0] - 4 * cm)
            if n_cols == 2:
                col_widths = [ancho_total * 0.28, ancho_total * 0.72]
            else:
                col_widths = [ancho_total / n_cols] * n_cols
            tabla = Table(datos, colWidths=col_widths, repeatRows=1)
            tabla.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2545")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C7D0D8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tabla)
            story.append(Spacer(1, 10))
            continue

        # Línea de lista ("- texto") o párrafo normal: se acumula.
        if stripped.startswith("- "):
            flush_parrafo()
            story.append(Paragraph("&bull;&nbsp;&nbsp;" + inline_md(stripped[2:]), ESTILOS["cuerpo"]))
            i += 1
            continue

        parrafo_buf.append(stripped)
        i += 1

    flush_parrafo()
    return story


def _pie_pagina(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#666666"))
    canvas_obj.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
    canvas_obj.restoreState()


def main():
    with open(ENTRADA, "r", encoding="utf-8") as f:
        md_texto = f.read()

    doc = SimpleDocTemplate(
        SALIDA, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="Memoria Descriptiva y Justificativa del Software — Smart Manager",
        author="Mohamed Assbai Ahammar",
    )
    story = construir_story(md_texto)
    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"Generado: {SALIDA}")


if __name__ == "__main__":
    main()
