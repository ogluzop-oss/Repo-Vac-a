"""
Etiqueta imprimible de PEDIDO con CÓDIGO QR para trazabilidad de costes.

Se genera EN LA TRAMITACIÓN del pedido (no en la recepción) y está pensada para enviarla al proveedor,
que la adhiere a los palés/cajas; al recepcionar, el QR permite identificar el pedido y su coste pactado.
El QR codifica la referencia y el UUID del pedido (+ empresa/proveedor/fecha) en texto plano.

Degradable: si faltan `reportlab`/`qrcode`, no lanza; devuelve None y quien llama informa al usuario.
"""

import logging
import os

logger = logging.getLogger("utils.etiqueta_pedido")


def generar_etiqueta_pedido_pdf(datos: dict, archivo: str) -> str | None:
    """Genera una etiqueta A6-ish (media carta apaisada) con cabecera + QR + resumen de bultos.
    `datos`: {referencia, uuid, empresa, proveedor, fecha, lineas:[{codigo,descripcion,cantidad}],
    bultos, total}. Devuelve la ruta del PDF o None si no se pudo generar."""
    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A6
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.warning("etiqueta_pedido: reportlab no disponible: %s", e)
        return None

    ref = str(datos.get("referencia") or "")
    uuid_ = str(datos.get("uuid") or "")
    empresa = str(datos.get("empresa") or "")
    proveedor = str(datos.get("proveedor") or "")
    fecha = str(datos.get("fecha") or "")
    lineas = datos.get("lineas") or []
    bultos = datos.get("bultos")
    if bultos is None:
        bultos = sum(int(l.get("cantidad") or 0) for l in lineas)

    # Contenido del QR: identificación unívoca del pedido para la recepción/trazabilidad de costes.
    qr_payload = (f"SMART-PEDIDO\nREF:{ref}\nUUID:{uuid_}\nEMPRESA:{empresa}\n"
                  f"PROVEEDOR:{proveedor}\nFECHA:{fecha}\nBULTOS:{bultos}")

    try:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        ancho, alto = A6[1], A6[0]   # apaisado
        c = canvas.Canvas(archivo, pagesize=(ancho, alto))
        cyan = (0.0, 0.85, 0.70)

        # Marco
        c.setStrokeColorRGB(*cyan); c.setLineWidth(1.5)
        c.roundRect(5 * mm, 5 * mm, ancho - 10 * mm, alto - 10 * mm, 4 * mm, stroke=1, fill=0)

        # Cabecera
        c.setFillColorRGB(*cyan)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(10 * mm, alto - 13 * mm, "ETIQUETA DE PEDIDO")
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(10 * mm, alto - 19 * mm, f"Ref: {ref}")

        # QR (arriba-derecha)
        qr_dim = 34 * mm
        try:
            import qrcode
            img = qrcode.make(qr_payload)
            buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
            c.drawImage(ImageReader(buf), ancho - qr_dim - 8 * mm, alto - qr_dim - 8 * mm,
                        qr_dim, qr_dim, preserveAspectRatio=True, mask="auto")
        except Exception as e:
            logger.warning("etiqueta_pedido: QR no generado: %s", e)

        # Datos
        c.setFont("Helvetica", 9)
        y = alto - 27 * mm
        for etiqueta, valor in (("Empresa", empresa), ("Proveedor", proveedor), ("Fecha", fecha),
                                ("Bultos/uds", str(bultos))):
            c.setFillColorRGB(0.45, 0.45, 0.45); c.drawString(10 * mm, y, f"{etiqueta}:")
            c.setFillColorRGB(0, 0, 0); c.drawString(32 * mm, y, valor[:40])
            y -= 5.2 * mm

        # Resumen de artículos (primeras líneas)
        c.setFillColorRGB(*cyan); c.setFont("Helvetica-Bold", 8.5)
        c.drawString(10 * mm, y, "Resumen:"); y -= 4.6 * mm
        c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 8)
        for l in lineas[:6]:
            txt = f"{int(l.get('cantidad') or 0):>3}  x  {str(l.get('descripcion') or l.get('codigo') or '')[:34]}"
            c.drawString(10 * mm, y, txt); y -= 4.2 * mm
        if len(lineas) > 6:
            c.drawString(10 * mm, y, f"… (+{len(lineas) - 6} artículos)")

        # UUID pie
        c.setFillColorRGB(0.5, 0.5, 0.5); c.setFont("Helvetica", 6.5)
        c.drawString(10 * mm, 8 * mm, f"UUID: {uuid_}")
        c.showPage(); c.save()
        return archivo
    except Exception as e:
        logger.error("generar_etiqueta_pedido_pdf: %s", e)
        return None
