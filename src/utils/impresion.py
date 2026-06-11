# src/utils/impresion.py
"""Módulo para impresión de tickets usando reportlab y escpos.

PLANTILLA DE REFERENCIA i18n para documentos:
  - Etiquetas fijas  → i18n.tr("ticket.*")            (Nivel 1, instantáneo)
  - Contenido dinámico (nombres de artículo) → ai_translator.traducir_lote(...)
    en UNA sola llamada por documento                 (Nivel 2, IA + caché)
El mismo patrón se replica en albaranes, facturas, contratos, nóminas, etc.
"""
import logging

from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from src.utils import divisas

logger = logging.getLogger(__name__)


# ============================================================
# BLOQUE i18n PARA DOCUMENTOS (helpers reutilizables)
# ============================================================

# Mapa de formas de pago (texto crudo → clave de traducción).
_FORMAS_PAGO = {
    "efectivo": "pay_cash", "cash": "pay_cash",
    "tarjeta": "pay_card", "card": "pay_card",
    "vale tienda": "pay_voucher", "vale": "pay_voucher",
}


def _doc_idioma(idioma=None):
    """Idioma activo de la app (o el indicado)."""
    if idioma:
        return idioma
    try:
        from src.utils import i18n
        return i18n.current_language()
    except Exception:
        return "es"


def _doc_tr(clave, defecto):
    """Etiqueta fija traducida (Nivel 1)."""
    try:
        from src.utils import i18n
        return i18n.tr(clave, default=defecto)
    except Exception:
        return defecto


def _doc_traducir_lote(textos, idioma, dominio):
    """Traducción IA por lotes con degradación elegante (Nivel 2)."""
    try:
        from src.utils import ai_translator
        return ai_translator.traducir_lote(list(textos), idioma, dominio=dominio)
    except Exception:
        return list(textos)


# ============================================================
# BLOQUE GENERACIÓN DE TICKET EN PDF (multiidioma)
# ============================================================

def generar_ticket_pdf(datos: dict, archivo: str = "ticket.pdf", idioma: str = None):
    """Genera un ticket de venta en PDF en el idioma activo.

    Nota: las fuentes base de reportlab (Helvetica) cubren alfabetos latinos;
    para chino, árabe, tailandés, etc. habría que incrustar una fuente Unicode
    (TTF) — mejora futura, no afecta a es/en/fr/de/it/pt.
    """
    lang = _doc_idioma(idioma)
    try:
        from src.utils import pdf_fonts
        _FN, _FB = pdf_fonts.fuentes_para(lang)
    except Exception:
        _FN, _FB = "Helvetica", "Helvetica-Bold"

    def L(clave, defecto):
        return _doc_tr(f"ticket.{clave}", defecto)

    items = datos.get("items", [])
    # Nivel 2: nombres de artículo traducidos en UNA sola llamada (caché incl.).
    nombres = [str(it.get("nombre", "")) for it in items]
    nombres_tr = _doc_traducir_lote(nombres, lang, dominio="tpv")

    # Forma de pago: etiqueta controlada → traducción local.
    fp_raw = str(datos.get("forma_pago", "")).strip().lower()
    if fp_raw in _FORMAS_PAGO:
        forma_pago = L(_FORMAS_PAGO[fp_raw], datos.get("forma_pago", ""))
    else:
        forma_pago = datos.get("forma_pago", "")

    # Altura dinámica para que quepan todas las líneas (+ cabecera de empresa).
    _extra = 0.4 if (datos.get("cif") or datos.get("empresa_dir")) else 0
    alto = (3.4 + _extra + 0.22 * max(len(items), 1)) * inch
    c = canvas.Canvas(archivo, pagesize=(3 * inch, alto))
    x = 0.2 * inch
    y = alto - 0.3 * inch

    _titulo = str(datos.get("empresa") or L("title", "SMART MANAGER"))
    _ts = 12
    while _ts > 7 and c.stringWidth(_titulo, _FB, _ts) > (2.8 * inch - x):
        _ts -= 0.5
    c.setFont(_FB, _ts)
    c.drawString(x, y, _titulo); y -= 0.26 * inch
    _subt = [s for s in [(f"CIF: {datos.get('cif')}" if datos.get("cif") else ""),
                         datos.get("empresa_dir") or ""] if s]
    if _subt:
        c.setFont(_FN, 7)
        for s in _subt:
            c.drawString(x, y, str(s)); y -= 0.14 * inch
        y -= 0.04 * inch

    c.setFont(_FN, 8)
    c.drawString(x, y, f"{L('date', 'Fecha')}: {datos.get('fecha', '-')}"); y -= 0.18 * inch
    if datos.get("venta_id") is not None:
        c.drawString(x, y, f"{L('sale', 'Venta')}: {datos.get('venta_id')}"); y -= 0.18 * inch
    if datos.get("caja") is not None:
        c.drawString(x, y, f"{L('register', 'Caja')}: {datos.get('caja')}"); y -= 0.18 * inch
    if datos.get("empleado") not in (None, ""):
        c.drawString(x, y, f"{L('employee', 'Empleado')}: {datos.get('empleado')}"); y -= 0.18 * inch
    y -= 0.06 * inch
    c.line(x, y, 2.8 * inch, y); y -= 0.16 * inch

    c.setFont(_FN, 8)
    for i, item in enumerate(items):
        nombre = nombres_tr[i] if i < len(nombres_tr) else item.get("nombre", "")
        cant = item.get("cantidad", 1)
        precio = item.get("precio", 0)
        c.drawString(x, y, f"{nombre}  x{cant}  {divisas.formatear(precio)}"); y -= 0.18 * inch

    y -= 0.04 * inch
    c.line(x, y, 2.8 * inch, y); y -= 0.18 * inch

    c.setFont(_FB, 10)
    c.drawString(x, y, f"{L('total', 'Total')}: {divisas.formatear(datos.get('total', 0))}"); y -= 0.2 * inch
    if datos.get("cambio"):
        c.setFont(_FN, 8)
        c.drawString(x, y, f"{L('change', 'Cambio')}: {divisas.formatear(datos.get('cambio'))}"); y -= 0.18 * inch
    if forma_pago:
        c.setFont(_FN, 8)
        c.drawString(x, y, f"{L('payment', 'Forma de pago')}: {forma_pago}"); y -= 0.22 * inch

    c.setFont(_FN, 8)
    c.drawString(x, y, L("thanks", "¡Gracias por su compra!"))
    c.save()
    logger.info(f"Ticket PDF generado ({lang}): {archivo}")


# ============================================================
# BLOQUE IMPRESIÓN EN IMPRESORA TÉRMICA
# ============================================================

def imprimir_ticket_termico(datos: dict, idioma: str = None):
    """Imprime el ticket en impresora térmica USB, en el idioma activo."""
    try:
        lang = _doc_idioma(idioma)

        def L(clave, defecto):
            return _doc_tr(f"ticket.{clave}", defecto)

        items = datos.get("items", [])
        nombres_tr = _doc_traducir_lote(
            [str(it.get("nombre", "")) for it in items], lang, dominio="tpv"
        )

        from escpos.printer import Usb
        printer = Usb(0x04B8, 0x0202)
        printer.set(align="center", font="a", bold=True, width=2, height=2)
        printer.text(L("title", "SMART MANAGER") + "\n")
        printer.set(align="left")
        printer.text(f"{L('date', 'Fecha')}: {datos.get('fecha')}\n")
        for i, item in enumerate(items):
            nombre = nombres_tr[i] if i < len(nombres_tr) else item.get("nombre", "")
            printer.text(f"{nombre} x{item.get('cantidad', 1)} {divisas.formatear(item.get('precio', 0))}\n")
        printer.text(f"{L('total', 'Total')}: {divisas.formatear(datos.get('total'))}\n")
        printer.text(L("thanks", "¡Gracias por su compra!") + "\n")
        printer.cut()
        printer.close()
        logger.info("Ticket impreso en térmica.")
    except Exception as e:
        logger.error(f"Error imprimiendo térmica: {e}")
