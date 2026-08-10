"""
FASE 3.8 — Distribución documental de la factura (exportación + envío).

Orquesta la exportación (PDF/Facturae) y el envío (email/FACe) reutilizando lo existente:
- PDF/Facturae desde el SNAPSHOT inmutable (factura_pdf / facturae_factura).
- Email vía `src.services.correo.servicio.enviar_documento` (Gmail OAuth ya existente).
Registra SIEMPRE la exportación/envío (factura_exportaciones / factura_envios) → trazabilidad
completa. Best-effort: nunca rompe el flujo de facturación.
"""

import logging

logger = logging.getLogger("facturacion.distribucion")


def exportar_factura(id_factura, formato="pdf", id_empresa=None) -> str | None:
    """Exporta la factura al formato indicado DESDE EL SNAPSHOT y registra la exportación.
    formato: 'pdf' | 'facturae'. Devuelve la ruta del fichero generado."""
    from src.db import facturas_cliente as FC
    formato = (formato or "pdf").lower()
    if formato == "facturae":
        from src.services.facturacion import facturae_factura as FE
        return FE.guardar_facturae(id_factura, id_empresa)   # ya registra la exportación
    # PDF (reproducible desde el snapshot)
    try:
        from src.utils import factura_pdf
        snap = FC.obtener_snapshot(id_factura, id_empresa)
        ruta = factura_pdf.generar_pdf_desde_snapshot(snap) if snap else None
        if ruta:
            FC.registrar_exportacion(id_factura, formato="pdf", ruta=ruta, id_empresa=id_empresa)
        return ruta
    except Exception as e:
        logger.error("exportar_factura(%s,pdf): %s", id_factura, e)
        return None


def enviar_factura_email(id_factura, id_correo, destinatario=None, id_empresa=None) -> dict:
    """Envía la factura por email (PDF adjunto) reutilizando el correo corporativo existente y
    registra el envío. Si no hay destinatario, usa el email del cliente. Best-effort."""
    from src.db import facturas_cliente as FC
    f = FC.obtener_factura(id_factura, id_empresa) or {}
    dest = destinatario
    if not dest and f.get("id_cliente"):
        try:
            from src.db import clientes as CLI
            dest = (CLI.obtener_cliente(f["id_cliente"]) or {}).get("email")
        except Exception:
            dest = None
    ruta_pdf = exportar_factura(id_factura, "pdf", id_empresa)
    ok, msg = False, "canal de correo no disponible"
    try:
        from src.services.correo import servicio as CS
        asunto = f"Factura {f.get('numero')}"
        cuerpo = "Adjuntamos su factura. Gracias por su confianza."
        ok, msg = CS.enviar_documento(id_correo, dest, asunto, cuerpo,
                                      [ruta_pdf] if ruta_pdf else [])
    except Exception as e:
        msg = str(e)
    FC.registrar_envio(id_factura, canal="email", destinatario=dest,
                       estado="enviada" if ok else "error",
                       error=None if ok else (msg or "")[:400], id_empresa=id_empresa)
    return {"ok": bool(ok), "mensaje": msg, "destinatario": dest}
