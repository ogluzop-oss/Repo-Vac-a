"""
Generador AUTÓNOMO del recibo de salarios (nómina) — diseño limpio en blanco y negro, tipografía
Segoe UI (bold) y tablas con esquinas redondeadas. Desacoplado del asistente/wizard: recibe un `datos`
dict (los campos del formulario inline) y produce el PDF directamente.

Para los importes cotizados (SS, IRPF, bases, coste empresa) invoca el MOTOR único existente
(`nomina_servicio.calcular_desde_datos`); no recalcula cotizaciones. Los conceptos de devengo se
muestran con el detalle introducido en el formulario.
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
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from src.utils import divisas

# ── Grupos de campos (compartidos con el formulario inline) ───────────────────
# (clave, etiqueta). Los importes por defecto son 0.
EMPRESA_CAMPOS = [
    ("razon_social", "Razón social"), ("nombre_comercial", "Nombre comercial"),
    ("cif", "CIF"), ("ccc", "Código Cuenta de Cotización (CCC)"),
    ("domicilio", "Domicilio"), ("cp", "Código Postal"), ("municipio", "Municipio"),
    ("provincia", "Provincia"), ("telefono", "Teléfono"), ("email", "Email"),
    ("cnae", "CNAE"), ("convenio", "Convenio colectivo"),
]
TRABAJADOR_CAMPOS = [
    ("trab_nombre", "Nombre"), ("trab_apellido1", "Primer apellido"),
    ("trab_apellido2", "Segundo apellido"), ("nif", "DNI/NIE/Pasaporte"),
    ("num_ss", "Nº afiliación S.S."), ("categoria", "Categoría profesional"),
    ("grupo_prof", "Grupo profesional"), ("grupo_cotizacion", "Grupo de cotización"),
    ("puesto", "Puesto de trabajo"), ("tipo_contrato", "Tipo de contrato"),
    ("codigo_contrato", "Código de contrato"), ("fecha_alta", "Fecha de alta"),
    ("antiguedad", "Antigüedad"), ("centro_trabajo", "Centro de trabajo"),
    ("departamento", "Departamento"), ("jornada", "Jornada"),
    ("jornada_pct", "% jornada"), ("horas_contratadas", "Horas contratadas"),
    ("trab_direccion", "Dirección"), ("trab_cp", "Código Postal"),
    ("trab_municipio", "Municipio"), ("trab_provincia", "Provincia"),
]
PERIODO_CAMPOS = [
    ("periodo_mes", "Mes"), ("periodo_anio", "Año"), ("periodo_inicio", "Fecha inicio"),
    ("periodo_fin", "Fecha fin"), ("periodo_dias", "Nº días liquidados"),
]
# Percepciones SALARIALES (cotizan).
DEVENGOS_SALARIALES = [
    ("salario_base", "Salario base"), ("complemento_personal", "Complemento personal"),
    ("complemento_antiguedad", "Complemento de antigüedad"), ("plus_convenio", "Plus convenio"),
    ("plus_transporte_sal", "Plus transporte"), ("plus_distancia", "Plus distancia"),
    ("plus_nocturnidad", "Plus nocturnidad"), ("plus_peligrosidad", "Plus peligrosidad"),
    ("plus_toxicidad", "Plus toxicidad"), ("plus_penosidad", "Plus penosidad"),
    ("plus_turnicidad", "Plus turnicidad"), ("plus_idiomas", "Plus idiomas"),
    ("incentivos", "Incentivos"), ("primas", "Primas"), ("comisiones", "Comisiones"),
    ("horas_extraordinarias", "Horas extraordinarias"),
    ("horas_complementarias", "Horas complementarias"),
    ("pagas_extra_prorrateadas", "Pagas extraordinarias prorrateadas"),
    ("mejora_voluntaria", "Mejora voluntaria"),
    ("complemento_puesto", "Complemento puesto de trabajo"),
    ("complemento_productividad", "Complemento productividad"),
    ("complemento_asistencia", "Complemento asistencia"),
    ("complemento_disponibilidad", "Complemento disponibilidad"),
    ("complemento_responsabilidad", "Complemento responsabilidad"),
    ("bonus", "Bonus"), ("otros_complementos", "Otros complementos"),
]
# Percepciones NO SALARIALES (no cotizan; tributa el exceso).
DEVENGOS_NO_SALARIALES = [
    ("dietas", "Dietas"), ("kilometraje", "Kilometraje"),
    ("gastos_locomocion", "Gastos de locomoción"), ("quebranto_moneda", "Quebranto de moneda"),
    ("desgaste_herramientas", "Desgaste herramientas"), ("indemnizaciones", "Indemnizaciones"),
    ("prestaciones_ss", "Prestaciones Seguridad Social"),
    ("otras_indemnizaciones", "Otras indemnizaciones"),
]
# Otras deducciones (además de SS e IRPF que calcula el motor).
OTRAS_DEDUCCIONES = [
    ("anticipos", "Anticipos"), ("embargos", "Embargos"),
    ("retribucion_flexible", "Retribución flexible"), ("cuotas_sindicales", "Cuotas sindicales"),
    ("cuota_colegio", "Cuota colegio profesional"), ("ausencias", "Ausencias"),
    ("otras_deducciones", "Otras deducciones"),
]
INFO_ADICIONAL = [
    ("iban", "IBAN de pago"), ("forma_pago", "Forma de pago"), ("fecha_pago", "Fecha de pago"),
    ("numero_nomina", "Número de nómina"),
]

_SS_TRAB = [("comunes", "Contingencias comunes"), ("desempleo", "Desempleo"),
            ("fp", "Formación profesional"), ("mei", "MEI"), ("horas_extra", "Horas extraordinarias")]
_SS_EMP = [("comunes", "Contingencias comunes"), ("at_ep", "Accidentes de trabajo"),
           ("desempleo", "Desempleo"), ("fp", "Formación"), ("fogasa", "FOGASA"), ("mei", "MEI")]

# ── Tipografía Segoe UI (bold + regular) con fallback Helvetica ───────────────
_FB, _FN = "Helvetica-Bold", "Helvetica"


def _registrar_fuentes():
    global _FB, _FN
    win = os.environ.get("WINDIR", "C:/Windows")
    fuentes = os.path.join(win, "Fonts")
    try:
        pb = os.path.join(fuentes, "segoeuib.ttf")
        pn = os.path.join(fuentes, "segoeui.ttf")
        if os.path.exists(pb):
            pdfmetrics.registerFont(TTFont("SegoeUI-Bold", pb)); _FB = "SegoeUI-Bold"
        if os.path.exists(pn):
            pdfmetrics.registerFont(TTFont("SegoeUI", pn)); _FN = "SegoeUI"
    except Exception:
        pass


_registrar_fuentes()

# Paleta blanco y negro.
NEGRO = colors.HexColor("#111111")
GRIS_CAB = colors.HexColor("#E9E9E9")
GRIS_FILA = colors.HexColor("#F6F6F6")
BORDE = colors.HexColor("#BBBBBB")
BLANCO = colors.white


def _num(datos, clave):
    from src.rrhh.nomina_servicio import num
    return num(datos.get(clave))


def _preparar_engine(datos: dict) -> dict:
    """Agrega los conceptos granulares del formulario en las claves que consume el motor, para que
    las BASES de cotización, SS, IRPF y coste-empresa sean correctas. El detalle se muestra aparte."""
    d = dict(datos or {})
    base = _num(datos, "salario_base")
    salariales_extra = sum(_num(datos, k) for k, _ in DEVENGOS_SALARIALES if k != "salario_base")
    no_sal = sum(_num(datos, k) for k, _ in DEVENGOS_NO_SALARIALES)
    d["salario"] = base
    d["bonus"] = round(salariales_extra, 2)   # todo lo salarial extra cotiza y tributa
    d["plus_convenio"] = 0
    d["nocturnidad"] = 0
    d["horas_extras"] = 0
    d["plus_transporte"] = 0
    d["dietas"] = round(no_sal, 2)             # no salarial (con exención en el motor)
    d["anticipos"] = _num(datos, "anticipos")
    d["embargos"] = _num(datos, "embargos")
    d["num_pagas"] = 12                         # el prorrateo se introduce como concepto, no se duplica
    return d


def generar_nomina_pdf(datos: dict, ruta: str = None) -> str:
    """Genera el PDF de la nómina y devuelve la ruta. `datos` = campos del formulario inline."""
    datos = datos or {}
    from src.rrhh.nomina_servicio import calcular_desde_datos
    res = calcular_desde_datos(_preparar_engine(datos))
    eur = divisas.formatear

    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "nominas")
        os.makedirs(folder, exist_ok=True)
        cod = (datos.get("nif") or "NOMINA")
        ruta = os.path.join(folder, f"NOMINA_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Recibo de salarios")
    usable_w = doc.width

    # Estilos.
    st_tit = ParagraphStyle("tit", fontName=_FB, fontSize=15, textColor=NEGRO, alignment=TA_CENTER,
                            leading=18)
    st_sub = ParagraphStyle("sub", fontName=_FN, fontSize=8.5, textColor=NEGRO, alignment=TA_CENTER,
                            leading=11)
    st_sec = ParagraphStyle("sec", fontName=_FB, fontSize=9.5, textColor=BLANCO, leading=13)
    st_lbl = ParagraphStyle("lbl", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
    st_val = ParagraphStyle("val", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10)
    st_cell = ParagraphStyle("cell", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10)
    st_cellr = ParagraphStyle("cellr", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10,
                              alignment=TA_RIGHT)
    st_th = ParagraphStyle("th", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
    st_thr = ParagraphStyle("thr", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10,
                            alignment=TA_RIGHT)
    st_tot = ParagraphStyle("tot", fontName=_FB, fontSize=8.5, textColor=NEGRO, leading=11)
    st_totr = ParagraphStyle("totr", fontName=_FB, fontSize=8.5, textColor=NEGRO, leading=11,
                             alignment=TA_RIGHT)

    _RADIO = [7, 7, 7, 7]

    def _seccion(titulo):
        t = Table([[Paragraph(titulo.upper(), st_sec)]], colWidths=[usable_w])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NEGRO),
            ("ROUNDEDCORNERS", _RADIO),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    def _grid_datos(campos, cols=2):
        """Tabla etiqueta:valor en `cols` columnas, esquinas redondeadas."""
        filas, fila = [], []
        for clave, etiqueta in campos:
            val = str(datos.get(clave) or "—")
            fila.append(Paragraph(f"{etiqueta}", st_lbl))
            fila.append(Paragraph(val, st_val))
            if len(fila) >= cols * 2:
                filas.append(fila); fila = []
        if fila:
            while len(fila) < cols * 2:
                fila.append(Paragraph("", st_val))
            filas.append(fila)
        if not filas:
            filas = [[Paragraph("—", st_val)]]
        cw = []
        for _ in range(cols):
            cw += [usable_w * 0.18, usable_w * (0.82 / cols - 0.18 + 0.18 * (cols - 1) / cols)]
        cw = ([usable_w * 0.16, usable_w * 0.34] * cols)[:cols * 2]
        t = Table(filas, colWidths=cw)
        t.setStyle(TableStyle([
            ("ROUNDEDCORNERS", _RADIO),
            ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BLANCO, GRIS_FILA]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        return t

    def _tabla_importes(titulo, filas, total_lbl, total_val):
        data = [[Paragraph(titulo, st_th), Paragraph("IMPORTE", st_thr)]]
        for concepto, importe in filas:
            data.append([Paragraph(concepto, st_cell), Paragraph(eur(importe), st_cellr)])
        data.append([Paragraph(total_lbl, st_tot), Paragraph(eur(total_val), st_totr)])
        t = Table(data, colWidths=[usable_w * 0.72, usable_w * 0.28])
        n = len(data)
        t.setStyle(TableStyle([
            ("ROUNDEDCORNERS", _RADIO),
            ("BACKGROUND", (0, 0), (-1, 0), GRIS_CAB),
            ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [BLANCO, GRIS_FILA]) if n > 2 else ("TEXTCOLOR", (0, 0), (0, 0), NEGRO),
            ("BACKGROUND", (0, -1), (-1, -1), GRIS_CAB),
            ("LINEABOVE", (0, -1), (-1, -1), 0.9, NEGRO),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return t

    def _total_row(titulo, valor, *, fuerte=False):
        """Fila-total destacada de una sola línea (sin cabecera redundante)."""
        t = Table([[Paragraph(titulo, st_tot), Paragraph(eur(valor), st_totr)]],
                  colWidths=[usable_w * 0.72, usable_w * 0.28])
        t.setStyle(TableStyle([
            ("ROUNDEDCORNERS", _RADIO),
            ("BACKGROUND", (0, 0), (-1, -1), GRIS_CAB),
            ("BOX", (0, 0), (-1, -1), 1.1 if fuerte else 0.8, NEGRO),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return t

    def _no_cero(campos):
        return [(et, _num(datos, k)) for k, et in campos if _num(datos, k)]

    story = []
    # Título.
    story.append(Paragraph("RECIBO INDIVIDUAL JUSTIFICATIVO DEL PAGO DE SALARIOS", st_tit))
    _mes = datos.get("periodo_mes") or ""
    _anio = datos.get("periodo_anio") or datetime.now().year
    story.append(Paragraph(f"Período de liquidación: {_mes} {_anio}"
                           f"  ·  Emitido el {datetime.now().strftime('%d/%m/%Y')}", st_sub))
    story.append(Spacer(1, 4 * mm))

    # Empresa / Trabajador / Período.
    story.append(_seccion("Datos de la empresa")); story.append(Spacer(1, 1.5 * mm))
    story.append(_grid_datos(EMPRESA_CAMPOS)); story.append(Spacer(1, 3 * mm))
    story.append(_seccion("Datos del trabajador/a")); story.append(Spacer(1, 1.5 * mm))
    story.append(_grid_datos(TRABAJADOR_CAMPOS)); story.append(Spacer(1, 3 * mm))
    story.append(_seccion("Período de liquidación")); story.append(Spacer(1, 1.5 * mm))
    story.append(_grid_datos(PERIODO_CAMPOS)); story.append(Spacer(1, 3 * mm))

    # Devengos.
    salariales = _no_cero(DEVENGOS_SALARIALES)
    no_sal = _no_cero(DEVENGOS_NO_SALARIALES)
    total_sal = round(sum(i for _, i in salariales), 2)
    total_nosal = round(sum(i for _, i in no_sal), 2)
    total_devengado = round(total_sal + total_nosal, 2)
    story.append(_seccion("Devengos")); story.append(Spacer(1, 1.5 * mm))
    story.append(_tabla_importes("I · PERCEPCIONES SALARIALES", salariales,
                                 "Subtotal salariales", total_sal))
    story.append(Spacer(1, 2 * mm))
    if no_sal:
        story.append(_tabla_importes("II · PERCEPCIONES NO SALARIALES", no_sal,
                                     "Subtotal no salariales", total_nosal))
        story.append(Spacer(1, 2 * mm))
    story.append(_total_row("A · TOTAL DEVENGADO", total_devengado, fuerte=True))
    story.append(Spacer(1, 3 * mm))

    # Deducciones.
    story.append(_seccion("Deducciones")); story.append(Spacer(1, 1.5 * mm))
    ss_filas = [(et, res.ss_trabajador.get(k, 0.0)) for k, et in _SS_TRAB if res.ss_trabajador.get(k, 0.0)]
    story.append(_tabla_importes("APORTACIONES DEL TRABAJADOR A LA S.S.", ss_filas,
                                 "Subtotal S.S.", res.ss_trabajador.get("total", 0.0)))
    story.append(Spacer(1, 2 * mm))
    story.append(_tabla_importes(f"RETENCIÓN IRPF ({res.irpf_tipo:.1f}%)", [], "IRPF", res.irpf_importe))
    story.append(Spacer(1, 2 * mm))
    otras = _no_cero(OTRAS_DEDUCCIONES)
    total_otras = round(sum(i for _, i in otras), 2)
    if otras:
        story.append(_tabla_importes("OTRAS DEDUCCIONES", otras, "Subtotal otras", total_otras))
        story.append(Spacer(1, 2 * mm))
    total_deducciones = round(res.ss_trabajador.get("total", 0.0) + res.irpf_importe + total_otras, 2)
    story.append(_total_row("B · TOTAL A DEDUCIR", total_deducciones, fuerte=True))
    story.append(Spacer(1, 3 * mm))

    # Líquido.
    liquido = round(total_devengado - total_deducciones, 2)
    liq = Table([[Paragraph("LÍQUIDO TOTAL A PERCIBIR (A − B)",
                            ParagraphStyle("lq", fontName=_FB, fontSize=12, textColor=NEGRO, leading=15)),
                  Paragraph(eur(liquido),
                            ParagraphStyle("lqr", fontName=_FB, fontSize=12, textColor=NEGRO, leading=15,
                                           alignment=TA_RIGHT))]],
                colWidths=[usable_w * 0.72, usable_w * 0.28])
    liq.setStyle(TableStyle([
        ("ROUNDEDCORNERS", _RADIO), ("BOX", (0, 0), (-1, -1), 1.4, NEGRO),
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CAB),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(liq); story.append(Spacer(1, 3 * mm))

    # Bases de cotización.
    story.append(_seccion("Determinación de las bases de cotización")); story.append(Spacer(1, 1.5 * mm))
    bases = [
        ("Base contingencias comunes", res.bccc), ("Base contingencias profesionales", res.bccp),
        ("Base AT/EP", res.base_at_ep), ("Base sujeta a IRPF", res.base_irpf),
    ]
    story.append(_grid_importes(usable_w, bases, eur, _RADIO, st_lbl, st_val))
    story.append(Spacer(1, 3 * mm))

    # Aportación empresarial + coste.
    story.append(_seccion("Aportación de la empresa (informativa)")); story.append(Spacer(1, 1.5 * mm))
    emp_filas = [(et, res.ss_empresa.get(k, 0.0)) for k, et in _SS_EMP if res.ss_empresa.get(k, 0.0)]
    coste = round(total_devengado + res.ss_empresa.get("total", 0.0), 2)
    story.append(_tabla_importes("COTIZACIÓN A CARGO DE LA EMPRESA", emp_filas,
                                 "Total cotización empresa", res.ss_empresa.get("total", 0.0)))
    story.append(Spacer(1, 2 * mm))
    story.append(_total_row("Coste total empresa (devengado + S.S.)", coste, fuerte=True))
    story.append(Spacer(1, 3 * mm))

    # Información adicional + firmas.
    story.append(_seccion("Información adicional")); story.append(Spacer(1, 1.5 * mm))
    story.append(_grid_datos(INFO_ADICIONAL)); story.append(Spacer(1, 4 * mm))

    firmas = Table([
        [Paragraph("Firma de la empresa", st_cell), Paragraph("Firma del trabajador/a (Recibí)", st_cell)],
        [Spacer(1, 1.5 * cm), Spacer(1, 1.5 * cm)],
        [Paragraph(str(datos.get("razon_social") or "—"), st_cell),
         Paragraph(f"{datos.get('trab_nombre') or ''} {datos.get('trab_apellido1') or ''}", st_cell)],
    ], colWidths=[usable_w / 2] * 2)
    firmas.setStyle(TableStyle([
        ("ROUNDEDCORNERS", _RADIO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(firmas)

    doc.build(story)
    return ruta


def _grid_importes(usable_w, filas, eur, radio, st_lbl, st_val):
    """Rejilla etiqueta:importe (2 columnas) con esquinas redondeadas — para las bases."""
    data, fila = [], []
    for et, val in filas:
        fila += [Paragraph(et, st_lbl), Paragraph(eur(val), ParagraphStyle(
            "vr", fontName=st_val.fontName, fontSize=8, alignment=TA_RIGHT, textColor=NEGRO))]
        if len(fila) >= 4:
            data.append(fila); fila = []
    if fila:
        while len(fila) < 4:
            fila.append(Paragraph("", st_val))
        data.append(fila)
    t = Table(data, colWidths=[usable_w * 0.30, usable_w * 0.20, usable_w * 0.30, usable_w * 0.20])
    t.setStyle(TableStyle([
        ("ROUNDEDCORNERS", radio), ("BOX", (0, 0), (-1, -1), 0.7, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BLANCO, GRIS_FILA]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t
