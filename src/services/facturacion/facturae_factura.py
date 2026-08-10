"""
FASE 3.5 — Puente Facturae/FACe para la FACTURA COMERCIAL.

Conecta la factura comercial (capa facturas_cliente) con el generador Facturae 3.2.x YA
EXISTENTE (`src.services.fiscal.facturae`), reutilizándolo (no se duplica el motor). El XML se
genera SIEMPRE desde el SNAPSHOT documental inmutable (nunca desde datos vivos), de modo que el
Facturae es idéntico al documento emitido aunque después cambien empresa/cliente/precios.

No envía nada por sí mismo: deja el XML listo (bytes/ruta). El envío real por FACe/FACeB2B se
encola en la FASE 3.8 (factura_envios), reutilizando los canales de `fiscal.facturae`.
"""

import logging
import os

logger = logging.getLogger("facturacion.facturae")


def _dir_facturae() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "documentos", "Facturae")
    os.makedirs(base, exist_ok=True)
    return base


def generar_facturae_factura(id_factura, id_empresa=None) -> bytes | None:
    """Genera el XML Facturae de una factura comercial DESDE SU SNAPSHOT. None si no procede."""
    try:
        from src.db import facturas_cliente as FC
        snap = FC.obtener_snapshot(id_factura, id_empresa)
        if not snap:
            return None
        # Proforma y similares NO fiscales no se exportan a Facturae.
        try:
            from src.services.facturacion import tipos_documento as TD
            if not TD.genera_fiscal((snap.get("factura") or {}).get("tipo_documento")):
                return None
        except Exception:
            pass
        from src.services.fiscal.facturae import facturae_xml as FX
        fdata = snap.get("factura") or {}
        lineas_pvp = [{"nombre": it.get("nombre"), "cantidad": it.get("cantidad"),
                       "precio": it.get("precio_unitario"), "subtotal": it.get("subtotal"),
                       "iva": it.get("iva")} for it in (snap.get("items") or [])]
        datos = FX.normalizar(
            emisor=snap.get("emisor") or {}, receptor=snap.get("cliente") or {},
            lineas_pvp=lineas_pvp, numero=fdata.get("numero"),
            fecha=fdata.get("fecha_emision"), id_empresa=id_empresa,
            moneda=snap.get("moneda") or "EUR")
        return FX.facturae_xml(datos)
    except Exception as e:
        logger.error("generar_facturae_factura(%s): %s", id_factura, e)
        return None


def guardar_facturae(id_factura, id_empresa=None) -> str | None:
    """Genera y guarda el XML Facturae en documentos/Facturae/ y devuelve la ruta.
    Registra la EXPORTACIÓN (FASE 3.8) si la API está disponible. Best-effort."""
    xml = generar_facturae_factura(id_factura, id_empresa)
    if not xml:
        return None
    try:
        from src.db import facturas_cliente as FC
        f = FC.obtener_factura(id_factura, id_empresa) or {}
        numero = f.get("numero") or f"FC{id_factura}"
        ruta = os.path.join(_dir_facturae(), f"{numero}.xml")
        with open(ruta, "wb") as fh:
            fh.write(xml)
        # Registro de exportación + evento (si existen en esta versión).
        try:
            FC.registrar_exportacion(id_factura, formato="facturae", ruta=ruta, id_empresa=id_empresa)
        except Exception:
            pass
        try:
            FC.registrar_evento(id_factura, "exportada", detalle=f"facturae:{os.path.basename(ruta)}",
                                id_empresa=id_empresa)
        except Exception:
            pass
        return ruta
    except Exception as e:
        logger.error("guardar_facturae(%s): %s", id_factura, e)
        return None
