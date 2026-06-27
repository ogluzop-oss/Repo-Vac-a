"""
Facturas SaaS (FASE P1.4): PDF, histórico, envío por correo y consulta desde el portal.
"""

import datetime as _dt
import logging
import os
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("saas.facturas")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def listar_facturas(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturas_saas WHERE id_empresa=%s ORDER BY id DESC", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_facturas: %s", e)
        return []


def _dir():
    base = os.path.join("documentos", "facturas_saas")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("facturas_saas")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def factura_pdf(id_factura, id_empresa=None) -> str | None:
    """Genera el PDF de una factura SaaS. Best-effort (sin reportlab → None)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturas_saas WHERE id=%s AND id_empresa=%s", (id_factura, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            f = _fila(cur, r)
    except Exception as e:
        logger.error("factura_pdf/leer: %s", e)
        return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception:
        return None
    nombre = "ACME"
    try:
        from src.services.saas import branding as _br
        nombre = (_br.obtener_branding(id_empresa) or {}).get("nombre_comercial") or nombre
    except Exception:
        pass
    ruta = os.path.join(_dir(), f"factura_saas_{f.get('numero') or id_factura}.pdf")
    try:
        c = canvas.Canvas(ruta, pagesize=A4); w, h = A4; y = h - 30 * mm
        c.setFont("Helvetica-Bold", 16); c.drawString(20 * mm, y, "Factura SaaS · Smart Manager")
        y -= 12 * mm; c.setFont("Helvetica", 11)
        for t in (f"Cliente: {nombre}", f"Nº factura: {f.get('numero')}", f"Fecha: {f.get('fecha')}",
                  f"Estado: {f.get('estado')}", f"Importe: {float(f.get('importe') or 0):.2f} EUR"):
            c.drawString(20 * mm, y, t); y -= 8 * mm
        c.save()
    except Exception as e:
        logger.error("factura_pdf: %s", e)
        return None
    _audit(id_empresa, f.get("numero"))
    return ruta


def enviar_factura(id_factura, id_correo, destinatario, id_empresa=None) -> bool:
    """Genera el PDF y lo envía por correo corporativo (best-effort)."""
    ruta = factura_pdf(id_factura, id_empresa=id_empresa)
    if not ruta:
        return False
    try:
        from src.services.correo import servicio as _c
        ok, _ = _c.enviar_documento(id_correo, destinatario, "Su factura SaaS",
                                    "Adjuntamos su factura.", adjuntos=[ruta])
        return ok
    except Exception as e:
        logger.error("enviar_factura: %s", e)
        return False


def _audit(id_empresa, numero):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "FACTURA_SAAS_PDF", "facturas_saas", f"{id_empresa}: {numero}")
    except Exception:
        pass
