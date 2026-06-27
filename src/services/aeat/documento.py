"""
Documento PDF común de declaraciones AEAT (FASE AEAT-2).

Generador de PDF por casillas reutilizable por cualquier modelo (303, 390, futuros): cabecera
de empresa/ejercicio/periodo, tabla de casillas, resultado, referencia y hash documental, y
alta en el registro documental (índice + hash). Evita duplicar la lógica de PDF entre modelos.
"""

import datetime as _dt
import logging
import os

from src.db.conexion import EMPRESA_DEFAULT_ID

logger = logging.getLogger("aeat.documento")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def dir_aeat():
    base = None
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("aeat")
    except Exception:
        base = os.path.join("documentos", "aeat")
    os.makedirs(base, exist_ok=True)
    return base


def _empresa_nombre(id_empresa):
    # FASE P1.3: el branding (nombre comercial) tiene prioridad en los documentos.
    try:
        from src.services.saas import branding as _br
        nc = (_br.obtener_branding(id_empresa) or {}).get("nombre_comercial")
        if nc:
            return nc
    except Exception:
        pass
    try:
        from src.db.empresa import obtener_empresa
        e = obtener_empresa(id_empresa) or {}
        return e.get("nombre_empresa") or e.get("razon_social") or str(id_empresa)
    except Exception:
        return str(id_empresa)


def generar_pdf(*, modelo, titulo, ejercicio, periodo, id_declaracion, casillas, resultado,
                sentido, hash_doc, id_empresa=None) -> str | None:
    """Genera el PDF de una declaración por casillas y lo registra en documentos_registro.
    Devuelve la ruta o None (best-effort: si falta reportlab, no rompe)."""
    id_empresa = _emp(id_empresa)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.info("reportlab no disponible, se omite PDF: %s", e)
        return None
    ruta = os.path.join(dir_aeat(), f"{modelo}_{ejercicio}_{periodo}_{id_declaracion}.pdf")
    ref = f"{modelo}-{ejercicio}-{periodo}-{id_declaracion}"
    try:
        c = canvas.Canvas(ruta, pagesize=A4)
        w, h = A4
        y = h - 25 * mm
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20 * mm, y, titulo)
        y -= 9 * mm
        c.setFont("Helvetica", 10)
        for txt in (f"Empresa: {_empresa_nombre(id_empresa)}",
                    f"Ejercicio: {ejercicio}   Periodo: {periodo}",
                    f"Fecha: {_dt.date.today().isoformat()}",
                    f"Referencia: {ref}"):
            c.drawString(20 * mm, y, txt); y -= 6 * mm
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "Casilla"); c.drawString(40 * mm, y, "Descripción")
        c.drawRightString(190 * mm, y, "Importe"); y -= 5 * mm
        c.setFont("Helvetica", 9)
        for cas in casillas:
            if y < 25 * mm:
                c.showPage(); y = h - 25 * mm; c.setFont("Helvetica", 9)
            c.drawString(20 * mm, y, str(cas["casilla"]))
            c.drawString(40 * mm, y, (cas.get("descripcion") or "")[:70])
            c.drawRightString(190 * mm, y, f"{float(cas['importe']):.2f}")
            y -= 5 * mm
        y -= 4 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, f"Resultado: {float(resultado):.2f} €  ({sentido})")
        y -= 10 * mm
        c.setFont("Helvetica", 7)
        c.drawString(20 * mm, y, f"Hash documental: {hash_doc}")
        c.save()
    except Exception as e:
        logger.error("generar_pdf %s: %s", modelo, e)
        return None
    try:
        from src.db import documentos as _doc
        _doc.registrar_documento(ruta, tipo="fiscal", nombre=os.path.basename(ruta),
                                 referencia=ref, importe=resultado, hash_documental=hash_doc,
                                 id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registro documental %s: %s", modelo, e)
    return ruta
