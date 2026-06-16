"""
Render de artefactos visuales del núcleo fiscal (C3.2) — QR.

Helper neutro: convierte el texto del QR fiscal (cadena cotejo Verifactu/TBAI o el
marcador del `simulado`) en un PNG. Degrada con elegancia si la librería `qrcode`
no está disponible (devuelve None) para no bloquear el flujo de venta.
"""

import logging

logger = logging.getLogger("fiscal.render")


def qr_png(texto: str, ruta: str | None = None) -> bytes | str | None:
    """Genera el QR de `texto`. Si se pasa `ruta`, lo guarda y devuelve la ruta;
    si no, devuelve los bytes PNG. Devuelve None si no se pudo generar."""
    if not texto:
        return None
    try:
        import qrcode
    except Exception as e:
        logger.debug("qrcode no disponible, se omite el render del QR: %s", e)
        return None
    try:
        img = qrcode.make(texto)
        if ruta:
            import os
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            img.save(ruta)
            return ruta
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning("No se pudo generar el QR fiscal: %s", e)
        return None
