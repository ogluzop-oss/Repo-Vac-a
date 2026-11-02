"""
Generador AUTÓNOMO del Modelo 145 AEAT — "Comunicación de datos al pagador" (art. 88 RIRPF). Mismo
patrón/librería que `nomina_pdf.py` (reportlab, blanco y negro, tipografía Segoe UI con fallback
Helvetica, tablas de esquinas redondeadas): recibe un `datos` dict (los campos ya recogidos/guardados
por `rrhh_modelo145_inline.py`) y produce el PDF directamente, sin depender de ningún wizard.

Replica el formato oficial: encabezado exacto + caja "Modelo 145" arriba a la derecha, los 7 bloques
numerados (1. Perceptor · 2. Hijos y otros descendientes · 3. Ascendientes · 4. Pensiones
compensatorias y anualidades por alimentos · 5. Deducción por vivienda habitual · 6. Fecha y firma
del perceptor · 7. Acuse de recibo de la empresa) y el pie de protección de datos (LO 3/2018).

NO calcula el % de IRPF (eso lo hace `src.rrhh.irpf_calculator.IRPFCalculatorService`) — si `datos`
trae `irpf_pct_calculado`, se muestra como nota informativa en el bloque 1, igual que el propio
Modelo 145 admite anotar el resultado de la comunicación.
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ── Catálogos compartidos con la GUI (mismos códigos que `rrhh_modelo145_inline.py` / BD) ──────────
SITUACIONES_FAMILIARES = {
    "1": "1ª — Soltero/a, viudo/a, divorciado/a o separado/a legalmente, con hijos que dan derecho "
         "al mínimo por descendientes",
    "2": "2ª — Casado/a y no separado/a legalmente, cuyo cónyuge no obtiene rentas anuales "
         "superiores a 1.500 € (excluidas las exentas)",
    "3": "3ª — Situación distinta de las anteriores",
}
GRADOS_DISCAPACIDAD = {
    "ninguna": "Ninguna",
    "menor_33": "Inferior al 33%",
    "entre_33_65": "Igual o superior al 33% e inferior al 65%",
    "mayor_65": "Igual o superior al 65%",
}

# ── Tipografía Segoe UI (bold + regular) con fallback Helvetica (idéntico a nomina_pdf.py) ─────────
_FB, _FN = "Helvetica-Bold", "Helvetica"


def _registrar_fuentes():
    global _FB, _FN
    win = os.environ.get("WINDIR", "C:/Windows")
    fuentes = os.path.join(win, "Fonts")
    try:
        pb = os.path.join(fuentes, "segoeuib.ttf")
        pn = os.path.join(fuentes, "segoeui.ttf")
        if os.path.exists(pb):
            pdfmetrics.registerFont(TTFont("SegoeUI-Bold-M145", pb)); _FB = "SegoeUI-Bold-M145"
        if os.path.exists(pn):
            pdfmetrics.registerFont(TTFont("SegoeUI-M145", pn)); _FN = "SegoeUI-M145"
    except Exception:
        pass


_registrar_fuentes()

NEGRO = colors.HexColor("#111111")
GRIS_CAB = colors.HexColor("#E9E9E9")
GRIS_FILA = colors.HexColor("#F6F6F6")
BORDE = colors.HexColor("#BBBBBB")
BLANCO = colors.white
_RADIO = [6, 6, 6, 6]


def _si_no(v) -> str:
    return "SÍ" if v else "NO"


def _txt(v) -> str:
    return "—" if v in (None, "") else str(v)


def generar_modelo145_pdf(datos: dict, ruta: str = None) -> str:
    """Genera el PDF del Modelo 145 y devuelve la ruta. `datos` (todas las claves opcionales salvo
    `nombre`/`nif`):

    Empresa: `emp_razon_social`, `emp_cif`.
    Perceptor: `nombre`, `nif`, `fecha_nacimiento`, `situacion_familiar` ('1'|'2'|'3'), `nif_conyuge`,
      `discapacidad_trabajador` (código de `GRADOS_DISCAPACIDAD`), `ayuda_terceros_movilidad` (bool),
      `movilidad_geografica` (bool), `rentas_irregulares` (bool), `irpf_pct_calculado` (informativo).
    `hijos`: lista de dicts {anio_nacimiento, anio_adopcion, grado_discapacidad, computo_entero}.
    `ascendientes`: lista de dicts {anio_nacimiento, grado_discapacidad, convivencia_otros_descendientes}.
    Pensiones: `pension_compensatoria_anual`, `anualidades_alimentos_anual`.
    Vivienda: `vivienda_habitual_pre2013` (bool).
    """
    datos = datos or {}
    hijos = datos.get("hijos") or []
    ascendientes = datos.get("ascendientes") or []

    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "modelo145")
        os.makedirs(folder, exist_ok=True)
        cod = (datos.get("nif") or "MODELO145")
        ruta = os.path.join(folder, f"MODELO145_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="Modelo 145 — Comunicación de datos al pagador")
    usable_w = doc.width

    st_tit = ParagraphStyle("tit", fontName=_FB, fontSize=11.5, textColor=NEGRO, leading=14)
    st_sub = ParagraphStyle("sub", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10.5)
    st_caja = ParagraphStyle("caja", fontName=_FB, fontSize=13, textColor=NEGRO, alignment=TA_CENTER,
                             leading=15)
    st_caja_sub = ParagraphStyle("cajasub", fontName=_FN, fontSize=7, textColor=NEGRO,
                                 alignment=TA_CENTER, leading=9)
    st_sec = ParagraphStyle("sec", fontName=_FB, fontSize=9.5, textColor=BLANCO, leading=13)
    st_lbl = ParagraphStyle("lbl", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
    st_val = ParagraphStyle("val", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10)
    st_th = ParagraphStyle("th", fontName=_FB, fontSize=7.6, textColor=NEGRO, leading=9.5)
    st_thc = ParagraphStyle("thc", fontName=_FB, fontSize=7.6, textColor=NEGRO, leading=9.5,
                            alignment=TA_CENTER)
    st_cell = ParagraphStyle("cell", fontName=_FN, fontSize=7.8, textColor=NEGRO, leading=10)
    st_cellc = ParagraphStyle("cellc", fontName=_FN, fontSize=7.8, textColor=NEGRO, leading=10,
                              alignment=TA_CENTER)
    st_pie = ParagraphStyle("pie", fontName=_FN, fontSize=6.4, textColor=colors.HexColor("#444444"),
                            leading=8.2, alignment=TA_LEFT)

    def _seccion(numero, titulo):
        t = Table([[Paragraph(f"{numero}. {titulo.upper()}", st_sec)]], colWidths=[usable_w])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NEGRO), ("ROUNDEDCORNERS", _RADIO),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    def _grid_datos(campos, cols=2):
        filas, fila = [], []
        for etiqueta, val in campos:
            fila.append(Paragraph(etiqueta, st_lbl))
            fila.append(Paragraph(_txt(val), st_val))
            if len(fila) >= cols * 2:
                filas.append(fila); fila = []
        if fila:
            while len(fila) < cols * 2:
                fila.append(Paragraph("", st_val))
            filas.append(fila)
        if not filas:
            filas = [[Paragraph("—", st_val)]]
        cw = ([usable_w * 0.18, usable_w * 0.32] * cols)[:cols * 2]
        t = Table(filas, colWidths=cw)
        t.setStyle(TableStyle([
            ("ROUNDEDCORNERS", _RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BLANCO, GRIS_FILA]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        return t

    def _tabla(cabeceras, filas_datos, anchos):
        data = [[Paragraph(c, st_thc) for c in cabeceras]]
        for f in filas_datos:
            data.append([Paragraph(str(v), st_cellc) for v in f])
        t = Table(data, colWidths=anchos)
        n = len(data)
        t.setStyle(TableStyle([
            ("ROUNDEDCORNERS", _RADIO), ("BACKGROUND", (0, 0), (-1, 0), GRIS_CAB),
            ("BOX", (0, 0), (-1, -1), 0.7, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_FILA]) if n > 1 else
            ("TEXTCOLOR", (0, 0), (0, 0), NEGRO),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    story = []

    # ── Encabezado + caja "Modelo 145" ─────────────────────────────────────────
    cab = Table([[
        Paragraph(
            "Impuesto sobre la Renta de las Personas Físicas<br/>"
            "Retenciones sobre rendimientos del trabajo<br/>"
            "Comunicación de datos al pagador (artículo 88 del Reglamento del IRPF)", st_tit),
        Table([[Paragraph("MODELO", st_caja_sub)], [Paragraph("145", st_caja)]],
              colWidths=[usable_w * 0.24]),
    ]], colWidths=[usable_w * 0.76, usable_w * 0.24])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (1, 0), (1, 0), 1.2, NEGRO), ("ROUNDEDCORNERS", _RADIO),
        ("TOPPADDING", (1, 0), (1, 0), 6), ("BOTTOMPADDING", (1, 0), (1, 0), 6),
    ]))
    story.append(cab)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Esta comunicación de datos, así como sus variaciones, surtirá efectos a partir de la fecha "
        "de su presentación, siempre que se presente con anterioridad a la fecha de pago de las "
        "correspondientes retribuciones.", st_sub))
    story.append(Spacer(1, 4 * mm))

    # ── 1. Perceptor ───────────────────────────────────────────────────────────
    story.append(_seccion(1, "Datos del perceptor")); story.append(Spacer(1, 1.5 * mm))
    story.append(_grid_datos([
        ("Apellidos y nombre", datos.get("nombre")), ("NIF/NIE", datos.get("nif")),
        ("Fecha de nacimiento", datos.get("fecha_nacimiento")),
        ("Empresa/pagador", datos.get("emp_razon_social")), ("CIF empresa", datos.get("emp_cif")),
    ]))
    story.append(Spacer(1, 1.5 * mm))
    situacion = str(datos.get("situacion_familiar") or "")
    story.append(_grid_datos([
        ("Situación familiar", SITUACIONES_FAMILIARES.get(situacion, "— Sin especificar —")),
        ("NIF del cónyuge (si situación 2ª)", datos.get("nif_conyuge")),
    ], cols=1))
    story.append(Spacer(1, 1.5 * mm))
    grado_trab = datos.get("discapacidad_trabajador") or "ninguna"
    story.append(_grid_datos([
        ("Grado de discapacidad del perceptor", GRADOS_DISCAPACIDAD.get(grado_trab, "Ninguna")),
        ("Movilidad reducida / ayuda de terceras personas", _si_no(datos.get("ayuda_terceros_movilidad"))),
        ("Movilidad geográfica (cambio de residencia por empleo)", _si_no(datos.get("movilidad_geografica"))),
        ("Rentas irregulares (con período de generación superior a 2 años)",
         _si_no(datos.get("rentas_irregulares"))),
    ]))
    if datos.get("irpf_pct_calculado") not in (None, ""):
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(
            f"<b>Tipo de retención resultante de la comunicación: "
            f"{datos.get('irpf_pct_calculado')}%</b> (calculado conforme al procedimiento general de "
            f"los arts. 80-87 del RIRPF — informativo, no forma parte del impreso oficial).", st_sub))
    story.append(Spacer(1, 3 * mm))

    # ── 2. Hijos y otros descendientes ────────────────────────────────────────
    story.append(_seccion(2, "Hijos y otros descendientes")); story.append(Spacer(1, 1.5 * mm))
    if hijos:
        filas = [[i + 1, _txt(h.get("anio_nacimiento")), _txt(h.get("anio_adopcion")),
                 GRADOS_DISCAPACIDAD.get(h.get("grado_discapacidad") or "ninguna", "Ninguna"),
                 _si_no(h.get("computo_entero"))]
                for i, h in enumerate(hijos)]
        story.append(_tabla(
            ["Nº", "Año nacimiento", "Año adopción", "Grado discapacidad", "Cómputo por entero"],
            filas, [usable_w * 0.08, usable_w * 0.18, usable_w * 0.18, usable_w * 0.38, usable_w * 0.18]))
    else:
        story.append(Paragraph("Sin hijos ni otros descendientes comunicados.", st_sub))
    story.append(Spacer(1, 3 * mm))

    # ── 3. Ascendientes ────────────────────────────────────────────────────────
    story.append(_seccion(3, "Ascendientes")); story.append(Spacer(1, 1.5 * mm))
    if ascendientes:
        filas = [[i + 1, _txt(a.get("anio_nacimiento")),
                 GRADOS_DISCAPACIDAD.get(a.get("grado_discapacidad") or "ninguna", "Ninguna"),
                 _si_no(a.get("convivencia_otros_descendientes"))]
                for i, a in enumerate(ascendientes)]
        story.append(_tabla(
            ["Nº", "Año nacimiento", "Grado discapacidad", "Convive con otros descendientes"],
            filas, [usable_w * 0.10, usable_w * 0.24, usable_w * 0.42, usable_w * 0.24]))
    else:
        story.append(Paragraph("Sin ascendientes comunicados.", st_sub))
    story.append(Spacer(1, 3 * mm))

    # ── 4. Pensiones compensatorias y anualidades por alimentos ───────────────
    story.append(_seccion(4, "Pensiones compensatorias y anualidades por alimentos"))
    story.append(Spacer(1, 1.5 * mm))
    from src.utils import divisas
    eur = divisas.formatear
    story.append(_grid_datos([
        ("Pensión compensatoria a favor del cónyuge (anual)",
         eur(datos.get("pension_compensatoria_anual") or 0)),
        ("Anualidades por alimentos en favor de los hijos (anual)",
         eur(datos.get("anualidades_alimentos_anual") or 0)),
    ]))
    story.append(Spacer(1, 3 * mm))

    # ── 5. Deducción por vivienda habitual ─────────────────────────────────────
    story.append(_seccion(5, "Deducción por adquisición o rehabilitación de la vivienda habitual"))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        f"Pagos por adquisición o rehabilitación de vivienda habitual con derecho a deducción "
        f"(contratos anteriores al 1 de enero de 2013, régimen transitorio — DT 18ª LIRPF): "
        f"<b>{_si_no(datos.get('vivienda_habitual_pre2013'))}</b>.", st_sub))
    story.append(Spacer(1, 3 * mm))

    # ── 6. Fecha y firma del perceptor ─────────────────────────────────────────
    story.append(_seccion(6, "Fecha y firma del perceptor")); story.append(Spacer(1, 1.5 * mm))
    fecha = datos.get("fecha") or datetime.now().strftime("%d/%m/%Y")
    firma1 = Table([
        [Paragraph(f"En ______________________, a {fecha}", st_cell)],
        [Spacer(1, 1.4 * cm)],
        [Paragraph(f"Firma: {_txt(datos.get('nombre'))} — NIF: {_txt(datos.get('nif'))}", st_cell)],
    ], colWidths=[usable_w])
    firma1.setStyle(TableStyle([
        ("ROUNDEDCORNERS", _RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(firma1)
    story.append(Spacer(1, 3 * mm))

    # ── 7. Acuse de recibo de la empresa ───────────────────────────────────────
    story.append(_seccion(7, "Acuse de recibo de la empresa")); story.append(Spacer(1, 1.5 * mm))
    firma2 = Table([
        [Paragraph(f"Recibido por {_txt(datos.get('emp_razon_social'))} — CIF: "
                  f"{_txt(datos.get('emp_cif'))}", st_cell)],
        [Spacer(1, 1.4 * cm)],
        [Paragraph("Fecha, firma y sello de la empresa:", st_cell)],
    ], colWidths=[usable_w])
    firma2.setStyle(TableStyle([
        ("ROUNDEDCORNERS", _RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(firma2)
    story.append(Spacer(1, 4 * mm))

    # ── Pie de protección de datos (LO 3/2018) ──────────────────────────────────
    story.append(Paragraph(
        "PROTECCIÓN DE DATOS: De conformidad con el Reglamento (UE) 2016/679 y la Ley Orgánica "
        "3/2018, de 5 de diciembre, de Protección de Datos Personales y garantía de los derechos "
        "digitales, los datos consignados en esta comunicación serán tratados por el pagador con la "
        "única finalidad de determinar el tipo de retención aplicable a los rendimientos del "
        "trabajo, no siendo objeto de cesión a terceros salvo obligación legal. El perceptor podrá "
        "ejercer sus derechos de acceso, rectificación, supresión y demás reconocidos por la "
        "normativa vigente ante el pagador.", st_pie))

    doc.build(story)
    # "Repositorio cifrado" (petición explícita) — ver nomina_pdf.py para el detalle del criterio.
    from src.utils import cripto
    cripto.cifrar_archivo_en_disco(ruta)
    return ruta
