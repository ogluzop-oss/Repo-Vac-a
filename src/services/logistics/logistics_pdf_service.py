"""
Enterprise logistics document PDF generation — Smart Manager AI.
Generates professional transfer documents (albaranes de traspaso) at
retail-enterprise level: full traceability, pallet QRs, signatures block,
incident placeholder, audit footer.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ─── Font registration ────────────────────────────────────────────────────────
_FR = "Helvetica"
_FB = "Helvetica-Bold"
_FI = "Helvetica-Oblique"

try:
    _win = r"C:\Windows\Fonts"
    pdfmetrics.registerFont(TTFont("SegoeUI", os.path.join(_win, "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("SegoeUI-Bold", os.path.join(_win, "segoeuib.ttf")))
    _FR, _FB = "SegoeUI", "SegoeUI-Bold"
except Exception:
    pass

# ─── Color palette ────────────────────────────────────────────────────────────
CN = colors.HexColor("#003366")   # Navy — section headers, table header bg
CWHT = colors.white               # White
CD = colors.HexColor("#212529")   # Near-black — body text
CG = colors.HexColor("#6c757d")   # Grey — labels, secondary text
CL = colors.HexColor("#f8f9fa")   # Light — alternating row bg
CB = colors.HexColor("#dee2e6")   # Border grey
CA = colors.HexColor("#0d6efd")   # Accent blue — state badge
CP = colors.HexColor("#e8f4fd")   # Pale blue — pale header row bg
CG2 = colors.HexColor("#d1e7dd")  # Green — received state
CO = colors.HexColor("#fff3cd")   # Orange — in-transit state
CR = colors.HexColor("#f8d7da")   # Red — incident state


# ─── Style helpers ────────────────────────────────────────────────────────────
def _S(name, size=9, bold=False, color=None, align=TA_LEFT, leading=None,
       sb=0, sa=0, font=None):
    return ParagraphStyle(
        name,
        fontName=font or (_FB if bold else _FR),
        fontSize=size,
        textColor=color or CD,
        alignment=align,
        leading=leading or max(size * 1.35, size + 2),
        spaceBefore=sb,
        spaceAfter=sa,
    )


# ─── Company info ─────────────────────────────────────────────────────────────
def _empresa() -> dict:
    d = {
        "nombre": "SMART MANAGER",
        "razon_social": "Smart Manager AI S.L.",
        "cif": "B-00000000",
        "direccion": "Dirección Fiscal, s/n — España",
        "telefono": "+34 000 000 000",
        "email": "info@smartmanagerai.local",
        "codigo_local": "ALMC",
    }
    try:
        # Fuente única de datos corporativos (FASE 2c).
        from src.db.empresa import info_documento
        info = info_documento()
        d["nombre"] = info.get("nombre") or d["nombre"]
        d["razon_social"] = info.get("razon_social") or info.get("nombre") or d["razon_social"]
        d["cif"] = info.get("cif") or d["cif"]
        d["direccion"] = info.get("direccion_completa") or d["direccion"]
        d["telefono"] = info.get("telefono") or d["telefono"]
        d["email"] = info.get("email") or d["email"]
        d["codigo_local"] = info.get("centro_codigo") or d["codigo_local"]
    except Exception:
        pass
    return d


# ─── QR helper ────────────────────────────────────────────────────────────────
def _qr_tmp(payload: dict) -> str:
    img = qrcode.make(json.dumps(payload, ensure_ascii=False, default=str))
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(f.name)
    f.close()
    return f.name


# ─── Public entry point ───────────────────────────────────────────────────────
def generar_albaran_traspaso(data: dict) -> str:
    """
    Generates a professional A4 enterprise transfer document.
    Returns the absolute path to the generated PDF.
    """
    emp = _empresa()
    id_doc = data.get("id_traspaso", "TRA-000")
    out_dir = Path(os.getcwd()) / "documentos" / "albaranes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / f"ALB_{id_doc}.pdf")

    qr_doc_tmp = _qr_tmp({
        "documento": id_doc,
        "tipo": "ALBARAN_TRASPASO",
        "origen": data.get("origen", ""),
        "destino": data.get("destino", ""),
        "agencia": data.get("agencia_transporte", ""),
        "estado": "EN_TRANSITO",
        "fecha": data.get("fecha_envio", datetime.now().strftime("%d/%m/%Y")),
    })

    try:
        _build(data, emp, out_path, qr_doc_tmp)
    finally:
        try:
            os.remove(qr_doc_tmp)
        except OSError:
            pass

    return out_path


# ─── PDF builder ──────────────────────────────────────────────────────────────
def _build(data: dict, emp: dict, out_path: str, qr_doc: str):
    PAGE_W, PAGE_H = A4
    ML, MR, MB = 16 * mm, 16 * mm, 20 * mm
    MT_FIRST = 12 * mm
    MT_LATER = 28 * mm
    CW_ = PAGE_W - ML - MR

    id_doc = data.get("id_traspaso", "TRA-000")
    fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")
    audit_id = f"AUD-{id_doc}"
    tipo_doc = data.get("tipo_documento", "ALBARÁN DE TRASPASO")

    def _on_first(c, doc):
        c.saveState()
        _draw_footer(c, doc, id_doc, fecha_gen, audit_id, PAGE_W, MB)
        c.restoreState()

    def _on_later(c, doc):
        c.saveState()
        _draw_mini_header(c, doc, emp, id_doc, tipo_doc, PAGE_W, PAGE_H, MT_LATER, ML)
        _draw_footer(c, doc, id_doc, fecha_gen, audit_id, PAGE_W, MB)
        c.restoreState()

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        title=f"{tipo_doc} — {id_doc}",
        author="Smart Manager AI",
        subject="Documento Logístico",
        creator="Smart Manager AI v2.4",
    )
    f_first = Frame(ML, MB, CW_, PAGE_H - MT_FIRST - MB, id="first")
    f_later = Frame(ML, MB, CW_, PAGE_H - MT_LATER - MB, id="later")
    doc.addPageTemplates([
        PageTemplate(id="First", frames=[f_first], onPage=_on_first),
        PageTemplate(id="Later", frames=[f_later], onPage=_on_later),
    ])

    story = _story(data, emp, qr_doc, CW_)
    doc.build(story)


# ─── Canvas decorations ───────────────────────────────────────────────────────
def _draw_footer(c, doc, id_doc, fecha_gen, audit_id, pw, mb):
    y = mb - 14 * mm
    c.setStrokeColor(CB)
    c.setLineWidth(0.4)
    c.line(16 * mm, y + 6 * mm, pw - 16 * mm, y + 6 * mm)
    c.setFont(_FR, 6.5)
    c.setFillColor(CG)
    left_txt = f"Documento generado por Smart Manager AI  |  Versión logística 2.4.1  |  {audit_id}"
    c.drawString(16 * mm, y + 2 * mm, left_txt)
    c.drawRightString(pw - 16 * mm, y + 2 * mm, f"Página {doc.page}  |  {fecha_gen}")


def _draw_mini_header(c, doc, emp, id_doc, tipo_doc, pw, ph, mt_later, ml):
    top = ph - 10 * mm
    c.setFillColor(CN)
    c.rect(0, ph - mt_later + 4 * mm, pw, mt_later - 4 * mm, fill=1, stroke=0)
    c.setFont(_FB, 8)
    c.setFillColor(CWHT)
    c.drawString(ml, top - 2 * mm, emp.get("nombre", "SMART MANAGER"))
    c.setFont(_FR, 8)
    c.drawCentredString(pw / 2, top - 2 * mm, tipo_doc)
    c.setFont(_FB, 8)
    c.drawRightString(pw - ml, top - 2 * mm, id_doc)
    c.setFont(_FR, 7)
    c.drawString(ml, top - 9 * mm, f"{emp.get('codigo_local', 'ALMC')} — {emp.get('email', '')}")
    c.setFont(_FR, 7)
    c.drawRightString(pw - ml, top - 9 * mm, "continuación →")
    c.setStrokeColor(colors.HexColor("#ffffff40"))
    c.setLineWidth(0.3)
    c.line(ml, ph - mt_later + 5 * mm, pw - ml, ph - mt_later + 5 * mm)


# ─── Story builder ────────────────────────────────────────────────────────────
def _story(data: dict, emp: dict, qr_doc: str, CW: float) -> list:
    story = []

    # ── 1. HEADER ─────────────────────────────────────────────────────────────
    story += _block_header(data, emp, qr_doc, CW)
    story.append(Spacer(1, 3 * mm))

    # ── 2. ORIGIN / DESTINATION ───────────────────────────────────────────────
    story += _block_logistica(data, CW)
    story.append(Spacer(1, 3 * mm))

    # ── 3. TRANSPORT ──────────────────────────────────────────────────────────
    story += _block_transporte(data, CW)
    story.append(Spacer(1, 4 * mm))

    # ── 4. ARTICLES TABLE ─────────────────────────────────────────────────────
    story.append(NextPageTemplate("Later"))
    story += _block_articulos(data, CW)
    story.append(Spacer(1, 4 * mm))

    # ── 5. SUMMARY ────────────────────────────────────────────────────────────
    story += _block_resumen(data, CW)
    story.append(Spacer(1, 3 * mm))

    # ── 6. INCIDENTS ──────────────────────────────────────────────────────────
    story += _block_incidencias(data, CW)
    story.append(Spacer(1, 3 * mm))

    # ── 7. TRACEABILITY ───────────────────────────────────────────────────────
    story += _block_trazabilidad(data, CW)
    story.append(Spacer(1, 3 * mm))

    # ── 8. SIGNATURES ─────────────────────────────────────────────────────────
    story += _block_firmas(data, CW)

    return story


# ─── Section: HEADER ─────────────────────────────────────────────────────────
def _block_header(data: dict, emp: dict, qr_doc: str, CW: float) -> list:
    s_company = _S("cmp_name", 13, bold=True, color=CWHT)
    s_cmp_sub = _S("cmp_sub", 7.5, color=colors.HexColor("#cce0ff"))
    s_doc_title = _S("doc_title", 18, bold=True, color=CWHT, align=TA_CENTER, leading=22)
    s_doc_id = _S("doc_id", 9, bold=True, color=colors.HexColor("#7ecfff"), align=TA_CENTER)
    s_doc_state = _S("doc_state", 8, color=colors.HexColor("#ffe066"), align=TA_CENTER)
    s_right = _S("hdr_right", 7, color=CWHT, align=TA_RIGHT)

    id_doc = data.get("id_traspaso", "—")
    fecha = data.get("fecha_envio", datetime.now().strftime("%d/%m/%Y"))
    tipo = data.get("tipo_documento", "ALBARÁN DE TRASPASO")

    left_cell = [
        Paragraph(emp.get("nombre", "SMART MANAGER"), s_company),
        Spacer(1, 1.5 * mm),
        Paragraph(emp.get("razon_social", ""), s_cmp_sub),
        Paragraph(f"CIF: {emp.get('cif', '—')}", s_cmp_sub),
        Paragraph(emp.get("direccion", "—"), s_cmp_sub),
        Paragraph(f"Tel: {emp.get('telefono', '—')}  |  {emp.get('email', '—')}", s_cmp_sub),
        Spacer(1, 2 * mm),
        Paragraph(f"ID CENTRO: {emp.get('codigo_local', 'ALMC')}", s_cmp_sub),
    ]

    center_cell = [
        Paragraph(tipo, s_doc_title),
        Spacer(1, 1.5 * mm),
        Paragraph(id_doc, s_doc_id),
        Paragraph(f"Fecha emisión: {fecha}", s_doc_state),
        Spacer(1, 2 * mm),
        Paragraph("Estado: EN TRÁNSITO", s_doc_state),
    ]

    qr_img = Image(qr_doc, 28 * mm, 28 * mm)
    right_cell = [
        qr_img,
        Spacer(1, 1.5 * mm),
        Paragraph("Escanear para trazabilidad", s_right),
    ]

    col_l = CW * 0.38
    col_c = CW * 0.38
    col_r = CW * 0.24

    header_tbl = Table(
        [[left_cell, center_cell, right_cell]],
        colWidths=[col_l, col_c, col_r],
    )
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 10),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    return [KeepTogether([header_tbl])]


# ─── Section: LOGISTICS BLOCK (origin / destination) ─────────────────────────
def _block_logistica(data: dict, CW: float) -> list:
    s_sec = _S("sec_lbl", 7, bold=True, color=CG, sa=2)
    s_center = _S("center_lbl", 10, bold=True, color=CD)
    s_field = _S("field_lbl", 7, bold=True, color=CG)
    s_val = _S("field_val", 9, color=CD)

    def _centro_block(titulo, nombre, codigo, responsable, fecha_lbl, fecha_val):
        rows = [
            [Paragraph(titulo, _S("ct_hdr", 8, bold=True, color=CWHT, align=TA_CENTER))],
            [Paragraph(nombre, _S("ct_nom", 11, bold=True, color=CD))],
            [Paragraph(f"Código: {codigo}", s_field)],
            [Spacer(1, 1 * mm)],
            [Paragraph(f"{responsable}", s_field)],
            [Paragraph(f"{fecha_lbl}: {fecha_val}", s_field)],
        ]
        t = Table(rows, colWidths=[(CW - 6 * mm) / 2])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), CN),
            ("BACKGROUND", (0, 1), (0, -1), CL),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, CB),
        ]))
        return t

    fecha = data.get("fecha_envio", "—")
    origen = data.get("origen", "—")
    destino = data.get("destino", "—")
    usuario = data.get("usuario", "—")
    agencia = data.get("agencia_transporte", "—")

    t_orig = _centro_block("ORIGEN / SALIDA", origen, origen,
                           f"Preparado por: {usuario}", "Fecha emisión", fecha)
    t_dest = _centro_block("DESTINO / RECEPCIÓN", destino, destino,
                           f"Agencia: {agencia}", "Fecha estimada", "—")

    outer = Table([[t_orig, t_dest]], colWidths=[CW / 2 - 3 * mm, CW / 2 - 3 * mm],
                  hAlign="LEFT")
    outer.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("INNERGRID", (0, 0), (-1, -1), 0, colors.transparent),
        ("BOX", (0, 0), (-1, -1), 0, colors.transparent),
        ("COLPADDING", (0, 0), (0, 0), 0),
    ]))

    return [KeepTogether([
        _sec_header("DETALLES DEL TRASPASO", CW),
        Spacer(1, 2 * mm),
        outer,
    ])]


# ─── Section: TRANSPORT ───────────────────────────────────────────────────────
def _block_transporte(data: dict, CW: float) -> list:
    pales = data.get("pales", [])
    n_pales = len(pales)
    n_refs = data.get("total_referencias", 0)
    peso_total = data.get("peso_total", "Pte.")
    agencia = data.get("agencia_transporte", "—")

    s = _S("tr_val", 8.5, color=CD)
    s_lbl = _S("tr_lbl", 7, bold=True, color=CG)

    def _field(lbl, val):
        return [Paragraph(lbl, s_lbl), Paragraph(str(val), s)]

    cols = [
        _field("TRANSPORTISTA", agencia),
        _field("Nº PALÉS / BULTOS", n_pales),
        _field("TOTAL REFERENCIAS", n_refs),
        _field("PESO TOTAL", peso_total),
        _field("MATRÍCULA", "—"),
        _field("TEMPERATURA", "Ambiente"),
    ]

    tbl_data = [cols]
    col_w = CW / len(cols)
    t = Table(tbl_data, colWidths=[col_w] * len(cols))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CL),
        ("BOX", (0, 0), (-1, -1), 0.5, CB),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, CB),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    return [KeepTogether([
        _sec_header("INFORMACIÓN DE TRANSPORTE", CW),
        Spacer(1, 2 * mm),
        t,
    ])]


# ─── Section: ARTICLES TABLE ──────────────────────────────────────────────────
def _block_articulos(data: dict, CW: float) -> list:
    s_th = _S("th", 8, bold=True, color=CWHT, align=TA_CENTER)
    s_pale_h = _S("pale_h", 9, bold=True, color=CWHT)
    s_pale_info = _S("pale_info", 7.5, color=colors.HexColor("#cce0ff"))
    s_ref = _S("ref", 8, color=CG)
    s_art = _S("art", 8.5, bold=True, color=CD)
    s_art_log = _S("art_log", 8, color=CG)
    s_num = _S("num", 8.5, bold=True, color=CD, align=TA_CENTER)
    s_num_s = _S("nums", 8, color=CG, align=TA_CENTER)
    s_estado = _S("est", 7.5, bold=True, color=CD, align=TA_CENTER)

    # Column widths (total = CW)
    W = [22 * mm, 78 * mm, 20 * mm, 22 * mm, 28 * mm]
    # Pad last col to fill CW exactly
    W[-1] = CW - sum(W[:-1])

    # Header row
    hdr = [
        Paragraph("REF", s_th),
        Paragraph("ARTÍCULO", s_th),
        Paragraph("CANT.", s_th),
        Paragraph("PESO", s_th),
        Paragraph("ESTADO", s_th),
    ]

    rows = [hdr]
    styles_spec = [
        ("BACKGROUND", (0, 0), (-1, 0), CN),
        ("GRID", (0, 0), (-1, -1), 0.4, CB),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    row_idx = 1
    for pale in data.get("pales", []):
        pale_id = pale.get("pale_codigo", "—")
        peso_pale = pale.get("peso_pale")
        peso_txt = f"{peso_pale:.2f} KG" if isinstance(peso_pale, (int, float)) else "PENDIENTE"
        arts = pale.get("articulos", [])
        n_uds = sum(a.get("cantidad", 0) for a in arts)

        # Palé header row (spans all columns)
        pale_hdr_content = [
            Paragraph(
                f"■  {pale_id}",
                s_pale_h,
            ),
            Paragraph(
                f"Peso: {peso_txt}   |   {len(arts)} referencia(s)   |   {n_uds} ud(s)",
                s_pale_info,
            ),
            "", "", "",
        ]
        rows.append(pale_hdr_content)
        styles_spec += [
            ("BACKGROUND", (0, row_idx), (-1, row_idx), CN),
            ("SPAN", (1, row_idx), (-1, row_idx)),
            ("FONTNAME", (0, row_idx), (-1, row_idx), _FB),
        ]
        row_idx += 1

        # Article rows
        for art_i, art in enumerate(arts):
            es_log = art.get("es_logistico", False)
            nombre = art.get("nombre", "—")
            codigo = art.get("codigo", "—")
            cantidad = art.get("cantidad", 0)

            if es_log:
                s_n = s_art_log
                estado_txt = "LOGÍSTICO"
                row_bg = CL
            else:
                s_n = s_art
                estado_txt = "EN TRÁNSITO"
                row_bg = CWHT if art_i % 2 == 0 else CL

            art_row = [
                Paragraph(codigo, s_ref),
                Paragraph(nombre, s_n),
                Paragraph(str(cantidad), s_num),
                Paragraph("—", s_num_s),
                Paragraph(estado_txt, s_estado),
            ]
            rows.append(art_row)
            if row_bg != CWHT:
                styles_spec.append(("BACKGROUND", (0, row_idx), (-1, row_idx), row_bg))
            if es_log:
                styles_spec.append(("TEXTCOLOR", (0, row_idx), (-1, row_idx), CG))
            row_idx += 1

        # Palé subtotal row
        sub_row = [
            "", "",
            Paragraph(f"{n_uds} ud(s)", _S("sub_u", 8, bold=True, color=CD, align=TA_CENTER)),
            Paragraph(peso_txt, _S("sub_p", 8, bold=True, color=CD, align=TA_CENTER)),
            Paragraph("TOTAL BULTO", _S("sub_lbl", 7.5, bold=True, color=CG, align=TA_CENTER)),
        ]
        rows.append(sub_row)
        styles_spec += [
            ("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#f0f4ff")),
            ("LINEABOVE", (0, row_idx), (-1, row_idx), 0.5, CN),
            ("LINEBELOW", (0, row_idx), (-1, row_idx), 0.8, CN),
        ]
        row_idx += 1

    t = Table(rows, colWidths=W, repeatRows=1, splitByRow=True)
    t.setStyle(TableStyle(styles_spec))

    return [
        _sec_header("RELACIÓN DE MERCANCÍA", CW),
        Spacer(1, 2 * mm),
        t,
    ]


# ─── Section: SUMMARY ─────────────────────────────────────────────────────────
def _block_resumen(data: dict, CW: float) -> list:
    pales = data.get("pales", [])
    n_pales = len(pales)
    total_refs = data.get("total_referencias", 0)
    total_uds = sum(
        sum(a.get("cantidad", 0) for a in p.get("articulos", []))
        for p in pales
    )
    peso_total = data.get("peso_total", "Pte.")

    s_lbl = _S("sum_lbl", 7.5, bold=True, color=CG)
    s_val = _S("sum_val", 14, bold=True, color=CN, align=TA_CENTER)

    fields = [
        ("TOTAL PALÉS / BULTOS", str(n_pales)),
        ("TOTAL REFERENCIAS", str(total_refs)),
        ("TOTAL UNIDADES", str(total_uds)),
        ("PESO TOTAL", str(peso_total)),
    ]

    w = CW / len(fields)
    cells = [[Paragraph(lbl, s_lbl), Paragraph(val, s_val)] for lbl, val in fields]

    # Transpose: one row of labels, one row of values
    row_lbls = [Paragraph(f, s_lbl) for f, _ in fields]
    row_vals = [Paragraph(v, s_val) for _, v in fields]

    t = Table([row_lbls, row_vals], colWidths=[w] * len(fields))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CL),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e8f0fe")),
        ("BOX", (0, 0), (-1, -1), 0.8, CN),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, CB),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    obs = data.get("observaciones", "")
    obs_block = []
    if obs:
        obs_block = [
            Spacer(1, 2 * mm),
            Paragraph("OBSERVACIONES", _S("obs_lbl", 7.5, bold=True, color=CG)),
            Paragraph(obs, _S("obs_val", 8.5, color=CD)),
        ]

    return [KeepTogether([
        _sec_header("RESUMEN LOGÍSTICO", CW),
        Spacer(1, 2 * mm),
        t,
        *obs_block,
    ])]


# ─── Section: INCIDENTS ───────────────────────────────────────────────────────
def _block_incidencias(data: dict, CW: float) -> list:
    s_th = _S("inc_th", 8, bold=True, color=CWHT, align=TA_CENTER)
    s_empty = _S("inc_empty", 8.5, color=CG, align=TA_CENTER)

    hdr = [
        Paragraph("TIPO", s_th),
        Paragraph("ARTÍCULO / REFERENCIA", s_th),
        Paragraph("CANTIDAD AFECTADA", s_th),
        Paragraph("OBSERVACIONES", s_th),
    ]
    # Placeholder empty row
    empty_row = [
        Paragraph("—", s_empty),
        Paragraph("Sin incidencias registradas", s_empty),
        Paragraph("—", s_empty),
        Paragraph("—", s_empty),
    ]

    W = [30 * mm, CW - 30 * mm - 35 * mm - 50 * mm, 35 * mm, 50 * mm]
    t = Table([hdr, empty_row], colWidths=W)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c0392b")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fef9f9")),
        ("GRID", (0, 0), (-1, -1), 0.4, CB),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))

    return [KeepTogether([
        _sec_header("INCIDENCIAS LOGÍSTICAS", CW),
        Spacer(1, 2 * mm),
        t,
    ])]


# ─── Section: TRACEABILITY ────────────────────────────────────────────────────
def _block_trazabilidad(data: dict, CW: float) -> list:
    usuario = data.get("usuario", "—")
    fecha = data.get("fecha_envio", datetime.now().strftime("%d/%m/%Y"))
    id_doc = data.get("id_traspaso", "—")

    s_th = _S("traz_th", 8, bold=True, color=CWHT, align=TA_CENTER)
    s_cell = _S("traz_cell", 8.5, color=CD)
    s_cell_c = _S("traz_cell_c", 8.5, color=CD, align=TA_CENTER)

    hdr = [Paragraph(h, s_th) for h in ["FECHA / HORA", "ESTADO", "USUARIO", "ACCIÓN"]]
    rows_data = [
        [fecha, "PREPARADO", usuario, "Creación del documento"],
        [fecha, "EN TRÁNSITO", usuario, f"Expedición {id_doc}"],
        ["—", "RECIBIDO", "—", "Pendiente de recepción"],
    ]
    state_colors = {
        "PREPARADO": colors.HexColor("#d1e7dd"),
        "EN TRÁNSITO": colors.HexColor("#fff3cd"),
        "RECIBIDO": colors.HexColor("#f8f9fa"),
    }

    tbl_data = [hdr]
    tbl_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), CN),
        ("GRID", (0, 0), (-1, -1), 0.4, CB),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, row in enumerate(rows_data):
        tbl_data.append([Paragraph(str(v), s_cell_c if j < 2 else s_cell)
                         for j, v in enumerate(row)])
        bg = state_colors.get(row[1], CWHT)
        tbl_styles.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))

    W = [35 * mm, 35 * mm, 40 * mm, CW - 110 * mm]
    t = Table(tbl_data, colWidths=W)
    t.setStyle(TableStyle(tbl_styles))

    return [KeepTogether([
        _sec_header("TRAZABILIDAD LOGÍSTICA", CW),
        Spacer(1, 2 * mm),
        t,
    ])]


# ─── Section: SIGNATURES ──────────────────────────────────────────────────────
def _block_firmas(data: dict, CW: float) -> list:
    s_titulo = _S("firma_titulo", 9, bold=True, color=CN)
    s_campo = _S("firma_campo", 7.5, color=CG)
    s_linea = _S("firma_linea", 7, color=CB)
    s_name = _S("firma_name", 8.5, color=CD)

    terminos = data.get("terminos", {})
    lbl_emisor = terminos.get("firma_emisor", "FIRMA EXPEDICIÓN")
    lbl_receptor = terminos.get("firma_receptor", "FIRMA RECEPCIÓN")
    usuario = data.get("usuario", "—")
    fecha = data.get("fecha_envio", "—")

    def _firma_block(titulo, nombre_default, fecha_val):
        return [
            Paragraph(titulo, s_titulo),
            Spacer(1, 2 * mm),
            Paragraph(f"Nombre: {nombre_default}", s_campo),
            Spacer(1, 14 * mm),
            HRFlowable(width="100%", thickness=0.8, color=CD),
            Spacer(1, 1 * mm),
            Paragraph(f"Fecha: {fecha_val}    Hora: ___________", s_campo),
            Spacer(1, 1 * mm),
            Paragraph("Firma y sello:", s_campo),
        ]

    firma_l = _firma_block(lbl_emisor, usuario, fecha)
    firma_r = _firma_block(lbl_receptor, "—", "—")

    half = CW / 2 - 6 * mm

    # Wrap each block in a Table for border
    def _wrap(block):
        t = Table([[block]], colWidths=[half])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, CB),
            ("BACKGROUND", (0, 0), (-1, -1), CL),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    outer = Table([[_wrap(firma_l), _wrap(firma_r)]], colWidths=[half + 6 * mm, half + 6 * mm])
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    return [KeepTogether([
        _sec_header("FIRMAS Y VALIDACIÓN", CW),
        Spacer(1, 2 * mm),
        outer,
        Spacer(1, 6 * mm),
    ])]


# ─── Helper: section header label ────────────────────────────────────────────
def _sec_header(text: str, CW: float) -> Table:
    s = _S("sh_lbl", 7.5, bold=True, color=CWHT)
    t = Table([[Paragraph(f"  {text}", s)]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CN),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t
