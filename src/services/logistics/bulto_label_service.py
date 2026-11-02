"""
Etiquetas de BULTO — Smart Manager AI.

Genera un PDF A4 sencillo (una etiqueta por bulto, varias por página) con el código de barras
Code128 del `id_bulto` para pegar físicamente sobre la caja antes de escanearla al recepcionarla
bulto a bulto (`gui/recepcion_pale.py::_ListaBultosPaleDialog`). Mismo patrón visual que
`pallet_label_service.py` (mismos colores/fuente), simplificado — no hace falta QR ni ruta/peso,
solo un identificador legible + su barcode escaneable.
"""

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

logger = logging.getLogger(__name__)

_FB = "Helvetica-Bold"
_FR = "Helvetica"


def generar_etiquetas_bultos(bultos: list, id_pale: str) -> str:
    """`bultos`: lista de dicts con al menos `id_bulto`/`id_visual`. Devuelve la ruta del PDF."""
    out_dir = Path(os.getcwd()) / "documentos" / "etiquetas_bultos"
    out_dir.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = str(out_dir / f"ETIQ_BULTOS_{_limpio(id_pale)}_{sello}.pdf")

    w, h = A4
    c = rl_canvas.Canvas(out_path, pagesize=A4)
    por_pagina = 6
    alto_etiqueta = h / por_pagina

    try:
        for i, bulto in enumerate(bultos or []):
            if i > 0 and i % por_pagina == 0:
                c.showPage()
            y_base = h - ((i % por_pagina) + 1) * alto_etiqueta

            c.setStrokeColorRGB(0.87, 0.89, 0.91)
            c.rect(10 * mm, y_base + 2 * mm, w - 20 * mm, alto_etiqueta - 4 * mm)

            c.setFont(_FB, 13)
            c.setFillColorRGB(0.0, 0.20, 0.40)
            c.drawString(16 * mm, y_base + alto_etiqueta - 10 * mm,
                        str(bulto.get("id_visual") or f"BULTO {i+1:02d}"))

            c.setFont(_FR, 8)
            c.setFillColorRGB(0.42, 0.46, 0.49)
            c.drawString(16 * mm, y_base + alto_etiqueta - 16 * mm, f"Palé: {id_pale}")

            id_bulto = str(bulto.get("id_bulto") or "")
            try:
                bc = code128.Code128(id_bulto, barHeight=10 * mm, barWidth=0.9)
                bc.drawOn(c, 16 * mm, y_base + 4 * mm)
            except Exception as e:
                logger.debug("barcode bulto %s: %s", id_bulto, e)
            c.setFont(_FR, 7)
            c.drawString(16 * mm, y_base + 1 * mm, id_bulto)
    finally:
        c.save()
    return out_path


def _limpio(valor: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(valor or ""))[:40]
