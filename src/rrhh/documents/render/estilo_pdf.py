"""
Helpers de diseño para los documentos RRHH en PDF: blanco y negro, tipografía Segoe UI (bold) y tablas
con esquinas redondeadas. Reutilizable por todos los generadores autónomos (nómina, alta, baja,
finiquito, certificados, cartas…). Diseño limpio, ordenado y agradable a la vista.
"""

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

# Paleta blanco y negro.
NEGRO = colors.HexColor("#111111")
GRIS_CAB = colors.HexColor("#E9E9E9")
GRIS_FILA = colors.HexColor("#F6F6F6")
BORDE = colors.HexColor("#BBBBBB")
BLANCO = colors.white
RADIO = [7, 7, 7, 7]

_FB, _FN = "Helvetica-Bold", "Helvetica"


def registrar_fuentes():
    """Registra Segoe UI (bold + regular) desde las fuentes de Windows. Fallback: Helvetica."""
    global _FB, _FN
    if _FB == "SegoeUI-Bold":
        return _FB, _FN
    fuentes = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
    try:
        pb, pn = os.path.join(fuentes, "segoeuib.ttf"), os.path.join(fuentes, "segoeui.ttf")
        if os.path.exists(pb):
            pdfmetrics.registerFont(TTFont("SegoeUI-Bold", pb)); _FB = "SegoeUI-Bold"
        if os.path.exists(pn):
            pdfmetrics.registerFont(TTFont("SegoeUI", pn)); _FN = "SegoeUI"
    except Exception:
        pass
    return _FB, _FN


def fuentes():
    return registrar_fuentes()


def estilos():
    """Diccionario de ParagraphStyle comunes."""
    fb, fn = registrar_fuentes()
    return {
        "tit": ParagraphStyle("tit", fontName=fb, fontSize=15, textColor=NEGRO, alignment=TA_CENTER, leading=18),
        "sub": ParagraphStyle("sub", fontName=fn, fontSize=8.5, textColor=NEGRO, alignment=TA_CENTER, leading=11),
        "sec": ParagraphStyle("sec", fontName=fb, fontSize=9.5, textColor=BLANCO, leading=13),
        "lbl": ParagraphStyle("lbl", fontName=fb, fontSize=8, textColor=NEGRO, leading=10),
        "val": ParagraphStyle("val", fontName=fn, fontSize=8, textColor=NEGRO, leading=10),
        "cell": ParagraphStyle("cell", fontName=fn, fontSize=8, textColor=NEGRO, leading=10),
        "cellr": ParagraphStyle("cellr", fontName=fn, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_RIGHT),
        "tot": ParagraphStyle("tot", fontName=fb, fontSize=8.5, textColor=NEGRO, leading=11),
        "totr": ParagraphStyle("totr", fontName=fb, fontSize=8.5, textColor=NEGRO, leading=11, alignment=TA_RIGHT),
        "just": ParagraphStyle("just", fontName=fn, fontSize=8.5, textColor=NEGRO, leading=12),
    }


def seccion(titulo, usable_w, sty):
    t = Table([[Paragraph(titulo.upper(), sty["sec"])]], colWidths=[usable_w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NEGRO), ("ROUNDEDCORNERS", RADIO),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def grid_datos(campos, datos, usable_w, sty, cols=2):
    """Rejilla etiqueta:valor en `cols` columnas, esquinas redondeadas."""
    filas, fila = [], []
    for clave, etiqueta in campos:
        val = str(datos.get(clave) or "—")
        fila += [Paragraph(etiqueta, sty["lbl"]), Paragraph(val, sty["val"])]
        if len(fila) >= cols * 2:
            filas.append(fila); fila = []
    if fila:
        while len(fila) < cols * 2:
            fila.append(Paragraph("", sty["val"]))
        filas.append(fila)
    if not filas:
        filas = [[Paragraph("—", sty["val"])]]
    # Anchuras que suman el total sea cual sea el nº de columnas (par etiqueta:valor por columna).
    par = usable_w / cols
    cw = [par * 0.32, par * 0.68] * cols
    t = Table(filas, colWidths=cw)
    t.setStyle(TableStyle([
        ("ROUNDEDCORNERS", RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BLANCO, GRIS_FILA]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _eur(v):
    from src.utils import divisas
    return divisas.formatear(v)


def tabla_importes(titulo, filas, total_lbl, total_val, usable_w, sty):
    """Tabla concepto:importe con cabecera, filas alternas y fila de total. Esquinas redondeadas."""
    data = [[Paragraph(titulo, sty["tot"]), Paragraph("IMPORTE", sty["totr"])]]
    for concepto, importe in filas:
        data.append([Paragraph(concepto, sty["cell"]), Paragraph(_eur(importe), sty["cellr"])])
    data.append([Paragraph(total_lbl, sty["tot"]), Paragraph(_eur(total_val), sty["totr"])])
    t = Table(data, colWidths=[usable_w * 0.72, usable_w * 0.28]); n = len(data)
    cmds = [
        ("ROUNDEDCORNERS", RADIO), ("BACKGROUND", (0, 0), (-1, 0), GRIS_CAB),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("BACKGROUND", (0, -1), (-1, -1), GRIS_CAB), ("LINEABOVE", (0, -1), (-1, -1), 0.9, NEGRO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if n > 2:
        cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [BLANCO, GRIS_FILA]))
    t.setStyle(TableStyle(cmds))
    return t


def tabla_columnas(columnas, filas, usable_w, sty):
    """Tabla con cabecera de columnas y N filas de datos. `columnas`=[(subclave,label),...];
    `filas`=[dict]. Esquinas redondeadas, filas alternas. Best-effort."""
    if not filas:
        filas = [{}]
    ncol = len(columnas)
    data = [[Paragraph(lbl, sty["lbl"]) for _, lbl in columnas]]
    for fila in filas:
        data.append([Paragraph(str(fila.get(sub) or "—"), sty["cell"]) for sub, _ in columnas])
    t = Table(data, colWidths=[usable_w / ncol] * ncol)
    n = len(data)
    cmds = [
        ("ROUNDEDCORNERS", RADIO), ("BACKGROUND", (0, 0), (-1, 0), GRIS_CAB),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    if n > 1:
        cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_FILA]))
    t.setStyle(TableStyle(cmds))
    return t


def total_row(titulo, valor, usable_w, sty, *, fuerte=True):
    t = Table([[Paragraph(titulo, sty["tot"]), Paragraph(_eur(valor), sty["totr"])]],
              colWidths=[usable_w * 0.72, usable_w * 0.28])
    t.setStyle(TableStyle([
        ("ROUNDEDCORNERS", RADIO), ("BACKGROUND", (0, 0), (-1, -1), GRIS_CAB),
        ("BOX", (0, 0), (-1, -1), 1.1 if fuerte else 0.8, NEGRO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def liquido_box(titulo, valor, usable_w, sty):
    fb, _ = registrar_fuentes()
    from reportlab.lib.styles import ParagraphStyle
    l = ParagraphStyle("lq", fontName=fb, fontSize=12, textColor=NEGRO, leading=15)
    r = ParagraphStyle("lqr", fontName=fb, fontSize=12, textColor=NEGRO, leading=15, alignment=TA_RIGHT)
    t = Table([[Paragraph(titulo, l), Paragraph(_eur(valor), r)]],
              colWidths=[usable_w * 0.72, usable_w * 0.28])
    t.setStyle(TableStyle([
        ("ROUNDEDCORNERS", RADIO), ("BOX", (0, 0), (-1, -1), 1.4, NEGRO),
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CAB),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def firmas(usable_w, sty, izq_titulo, izq_valor, der_titulo, der_valor):
    return firmas_cols(usable_w, sty, [(izq_titulo, izq_valor), (der_titulo, der_valor)])


def firmas_cols(usable_w, sty, columnas):
    """Bloque de firmas con N columnas: `columnas` = [(titulo, valor), ...]."""
    if not columnas:
        return Spacer(1, 1)
    n = len(columnas)
    fila_tit = [Paragraph(t or "", sty["cell"]) for t, _ in columnas]
    fila_esp = [Spacer(1, 1.5 * cm) for _ in columnas]
    fila_val = [Paragraph(v or "—", sty["cell"]) for _, v in columnas]
    t = Table([fila_tit, fila_esp, fila_val], colWidths=[usable_w / n] * n)
    t.setStyle(TableStyle([
        ("ROUNDEDCORNERS", RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t
