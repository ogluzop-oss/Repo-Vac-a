"""
Enterprise pallet label generation — Smart Manager AI.
Generates professional A4 sheets with 4 labels per page.
Each label includes: barcode, QR, route, pallet ID, weight, reference count.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import qrcode
from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

logger = logging.getLogger(__name__)

# ─── Font registration ────────────────────────────────────────────────────────
_FB = "Helvetica-Bold"
_FR = "Helvetica"
try:
    _win = r"C:\Windows\Fonts"
    pdfmetrics.registerFont(TTFont("SegoeUI", os.path.join(_win, "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("SegoeUI-Bold", os.path.join(_win, "segoeuib.ttf")))
    _FR, _FB = "SegoeUI", "SegoeUI-Bold"
except Exception:
    pass

# ─── Colors (RGB 0-1) ─────────────────────────────────────────────────────────
C_NAVY = (0.0, 0.20, 0.40)      # #003366
C_WHITE = (1.0, 1.0, 1.0)
C_DARK = (0.13, 0.16, 0.19)     # #212529
C_GREY = (0.42, 0.46, 0.49)     # #6c757d
C_LIGHT = (0.97, 0.98, 0.98)    # #f8f9fa
C_ACCENT = (0.05, 0.43, 0.99)   # #0d6efd
C_BORDER = (0.87, 0.89, 0.91)   # #dee2e6


# ─── Public entry point ───────────────────────────────────────────────────────
def generar_etiquetas_pales(
    lista_pales: list,
    origen: str,
    destino: str,
    id_traspaso: str,
) -> str:
    """
    Generates a PDF with 4 professional pallet labels per A4 page.
    Returns the absolute path to the generated PDF.
    """
    anio = datetime.now().year
    sec = str(id_traspaso).split("-")[-1].zfill(4)
    orig = _clean(origen)
    dest = _clean(destino)

    out_dir = Path(os.getcwd()) / "documentos" / "etiquetas_pales"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / f"ETIQ_{orig}_{sec}_{dest}_{anio}.pdf")

    W, H = A4
    c = rl_canvas.Canvas(out_path, pagesize=A4)

    # 4 label positions (quadrants)
    positions = [
        (0, H / 2),          # top-left
        (W / 2, H / 2),      # top-right
        (0, 0),              # bottom-left
        (W / 2, 0),          # bottom-right
    ]

    qr_cache: dict[str, str] = {}
    try:
        for i, pale_data in enumerate(lista_pales):
            if i > 0 and i % 4 == 0:
                c.showPage()
            x_off, y_off = positions[i % 4]

            # Generate QR for this pallet
            pale_id = pale_data.get("pale_codigo", f"PAL-{i+1:03d}")
            qr_content = json.dumps({
                "pale": pale_id,
                "doc": id_traspaso,
                "origen": origen,
                "destino": destino,
                "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            }, ensure_ascii=False)

            if pale_id not in qr_cache:
                tmp = _qr_tmp(qr_content)
                qr_cache[pale_id] = tmp

            _draw_label(c, x_off, y_off, W / 2, H / 2,
                        pale_data, orig, dest, id_traspaso,
                        sec, anio, qr_cache[pale_id])

        c.save()
    finally:
        for p in qr_cache.values():
            try:
                os.remove(p)
            except OSError:
                pass

    return out_path


# ─── Label drawing ────────────────────────────────────────────────────────────
def _draw_label(c, x0, y0, w, h, pale_data, orig, dest, id_traspaso, sec, anio, qr_path):
    """Draws a single label inside the quadrant (x0, y0, w, h)."""

    PAD = 4 * mm
    INN_X = x0 + PAD
    INN_Y = y0 + PAD
    INN_W = w - 2 * PAD
    INN_H = h - 2 * PAD

    pale_id = pale_data.get("pale_codigo", "—")
    peso = pale_data.get("peso_pale")
    peso_txt = f"{peso:.2f} KG" if isinstance(peso, (int, float)) else "PESO PENDIENTE"
    arts = pale_data.get("articulos", [])
    n_refs = len(arts)
    n_uds = sum(a.get("cantidad", 0) for a in arts)

    barcode_id = f"{pale_id.replace(' ', '').upper()}-{sec}-{orig}"
    # Trim barcode to safe length
    if len(barcode_id) > 40:
        barcode_id = barcode_id[:40]

    # ── Outer border ─────────────────────────────────────────────────────────
    c.setStrokeColorRGB(*C_NAVY)
    c.setLineWidth(1.2)
    c.rect(INN_X, INN_Y, INN_W, INN_H)

    # ── Navy header band ──────────────────────────────────────────────────────
    header_h = 16 * mm
    c.setFillColorRGB(*C_NAVY)
    c.rect(INN_X, INN_Y + INN_H - header_h, INN_W, header_h, fill=1, stroke=0)

    c.setFillColorRGB(*C_WHITE)
    c.setFont(_FB, 10)
    c.drawString(INN_X + 4 * mm, INN_Y + INN_H - 7.5 * mm, "SMART MANAGER — ETIQUETA LOGÍSTICA")
    c.setFont(_FR, 6.5)
    c.setFillColorRGB(0.8, 0.88, 1.0)  # light blue tint for secondary line
    c.drawString(INN_X + 4 * mm, INN_Y + INN_H - 13 * mm, f"DOC: {id_traspaso}")

    # ── Route bar ─────────────────────────────────────────────────────────────
    route_y = INN_Y + INN_H - header_h - 10 * mm
    c.setFillColorRGB(*C_LIGHT)
    c.rect(INN_X, route_y, INN_W, 10 * mm, fill=1, stroke=0)
    c.setStrokeColorRGB(*C_BORDER)
    c.setLineWidth(0.3)
    c.rect(INN_X, route_y, INN_W, 10 * mm, fill=0, stroke=1)

    c.setFillColorRGB(*C_NAVY)
    c.setFont(_FB, 13)
    route_text = f"{orig}  →  {dest}"
    c.drawCentredString(INN_X + INN_W / 2, route_y + 3 * mm, route_text)

    # ── Pallet ID large ───────────────────────────────────────────────────────
    pale_id_y = route_y - 14 * mm
    c.setFillColorRGB(*C_DARK)
    c.setFont(_FB, 22)
    c.drawCentredString(INN_X + INN_W / 2, pale_id_y + 3 * mm, pale_id)
    c.setFont(_FR, 7.5)
    c.setFillColorRGB(*C_GREY)
    c.drawCentredString(INN_X + INN_W / 2, pale_id_y - 2 * mm, "IDENTIFICADOR DE BULTO")

    # ── Barcode ───────────────────────────────────────────────────────────────
    bc_y = pale_id_y - 22 * mm
    try:
        bc = code128.Code128(barcode_id, barHeight=16 * mm, barWidth=1.1)
        bc_x = INN_X + (INN_W - bc.width) / 2
        bc.drawOn(c, bc_x, bc_y)
        c.setFont(_FR, 6)
        c.setFillColorRGB(*C_GREY)
        c.drawCentredString(INN_X + INN_W / 2, bc_y - 3 * mm, barcode_id)
    except Exception as e:
        logger.warning(f"Barcode error: {e}")
        bc_y += 16 * mm  # shift back up if barcode fails

    # ── QR + info block side by side ─────────────────────────────────────────
    qr_block_y = bc_y - 4 * mm - 26 * mm
    if qr_block_y < INN_Y + 4 * mm:
        qr_block_y = INN_Y + 4 * mm

    # QR on left
    try:
        c.drawImage(qr_path, INN_X + 2 * mm, qr_block_y, 26 * mm, 26 * mm)
    except Exception:
        pass

    # Info block on right of QR
    info_x = INN_X + 32 * mm
    c.setFont(_FB, 8)
    c.setFillColorRGB(*C_GREY)
    c.drawString(info_x, qr_block_y + 22 * mm, "PESO DECLARADO:")
    c.setFont(_FB, 14)
    c.setFillColorRGB(*C_NAVY)
    c.drawString(info_x, qr_block_y + 15 * mm, peso_txt)

    c.setFont(_FR, 7.5)
    c.setFillColorRGB(*C_GREY)
    c.drawString(info_x, qr_block_y + 10 * mm, f"Referencias: {n_refs}")
    c.drawString(info_x, qr_block_y + 5 * mm, f"Unidades: {n_uds}")

    # ── Bottom strip: generation date + system ────────────────────────────────
    strip_h = 6 * mm
    c.setFillColorRGB(*C_LIGHT)
    c.setStrokeColorRGB(*C_BORDER)
    c.setLineWidth(0.3)
    c.rect(INN_X, INN_Y, INN_W, strip_h, fill=1, stroke=1)
    c.setFillColorRGB(*C_GREY)
    c.setFont(_FR, 6.5)
    gen_txt = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   Smart Manager AI   |   {id_traspaso}"
    c.drawCentredString(INN_X + INN_W / 2, INN_Y + 1.8 * mm, gen_txt)

    # ── Single separator above QR/info block ─────────────────────────────────
    sep_y = qr_block_y + 28 * mm
    if INN_Y + strip_h + 2 * mm < sep_y < INN_Y + INN_H - header_h - 2 * mm:
        c.setStrokeColorRGB(*C_BORDER)
        c.setLineWidth(0.3)
        c.line(INN_X + 2 * mm, sep_y, INN_X + INN_W - 2 * mm, sep_y)


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _clean(s: str) -> str:
    return str(s).strip().upper().replace(" ", "_").replace("/", "-")[:20]


def _qr_tmp(content: str) -> str:
    img = qrcode.make(content)
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(f.name)
    f.close()
    return f.name
