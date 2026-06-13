# src/utils/impresion.py
"""Módulo para impresión de tickets usando reportlab y escpos.

PLANTILLA DE REFERENCIA i18n para documentos:
  - Etiquetas fijas  → i18n.tr("ticket.*")            (Nivel 1, instantáneo)
  - Contenido dinámico (nombres de artículo) → ai_translator.traducir_lote(...)
    en UNA sola llamada por documento                 (Nivel 2, IA + caché)
El mismo patrón se replica en albaranes, facturas, contratos, nóminas, etc.
"""
import logging
import os

from reportlab.lib.units import inch  # noqa: F401  (compat; el ticket usa mm)
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
    "mixto": "pay_mixed", "mixed": "pay_mixed",
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

def _ticket_imagen_codigo(tipo: str, dato: str):
    """Genera un código de barras (Code128) o QR como ImageReader de reportlab.
    Devuelve (ImageReader, ratio_alto/ancho) o (None, 0) si falla / no hay libs."""
    from io import BytesIO

    from reportlab.lib.utils import ImageReader
    try:
        if tipo == "qr":
            import qrcode
            img = qrcode.make(dato)
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return ImageReader(buf), 1.0
        import barcode
        from barcode.writer import ImageWriter
        clase = barcode.get_barcode_class("code128")
        bc = clase(str(dato), writer=ImageWriter())
        # render() devuelve directamente la PIL Image (evita bc.write(), que
        # rompe con Pillow >=10). write_text=False evita font.getsize (eliminado
        # en Pillow >=10); el nº ya se imprime arriba en el ticket.
        img = bc.render(writer_options={"module_height": 10.0, "write_text": False,
                                        "quiet_zone": 2.0})
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        ir = ImageReader(buf)
        w, h = ir.getSize()
        return ir, (h / w if w else 0.3)
    except Exception as e:
        logger.warning("No se pudo generar el código (%s): %s", tipo, e)
        return None, 0


def generar_ticket_pdf(datos: dict, archivo: str = "ticket.pdf", idioma: str = None):
    """Genera un ticket de compra PROFESIONAL en PDF (formato recibo 80 mm).

    Estructura (estilo retail): logo + cabecera fiscal, datos de operación,
    desglose de líneas (con descuentos y granel), subtotal/descuentos, tabla de
    IVA, TOTAL destacado, desglose de pago, código de barras + QR, política de
    devolución, mensaje de despedida y trazabilidad. Multidivisa y multiempresa.

    `datos` admite tanto el formato enriquecido (claves 'empresa', 'tienda',
    'operacion', 'pago', 'items' con iva/descuento/granel, 'config', 'hash')
    como el formato plano antiguo (degradación elegante).
    """
    from reportlab.lib.units import mm

    lang = _doc_idioma(idioma)
    try:
        from src.utils import pdf_fonts
        _FN, _FB = pdf_fonts.fuentes_para(lang)
    except Exception:
        _FN, _FB = "Helvetica", "Helvetica-Bold"

    def L(clave, defecto):
        return _doc_tr(f"ticket.{clave}", defecto)

    moneda = datos.get("moneda")

    def M(v):
        return divisas.formatear(v or 0, moneda)

    # ── Normalización de datos (acepta formato enriquecido o plano) ──────────
    emp = datos.get("empresa") or {}
    if not isinstance(emp, dict):  # formato antiguo: 'empresa' era el nombre
        emp = {"nombre": datos.get("empresa"), "cif": datos.get("cif"),
               "direccion_completa": datos.get("empresa_dir")}
    tienda = datos.get("tienda") or {}
    oper = datos.get("operacion") or {
        "fecha": datos.get("fecha"), "venta_id": datos.get("venta_id"),
        "caja": datos.get("caja"), "empleado": datos.get("empleado"),
    }
    pago = datos.get("pago") or {
        "forma_pago": datos.get("forma_pago"), "total": datos.get("total"),
        "cambio": datos.get("cambio"),
    }
    cfg = datos.get("config") or {}
    items = datos.get("items", [])

    # Nivel 2: nombres de artículo traducidos en UNA sola llamada (caché incl.).
    nombres = [str(it.get("nombre", "")) for it in items]
    nombres_tr = _doc_traducir_lote(nombres, lang, dominio="tpv")

    # ── Cálculos económicos ──────────────────────────────────────────────────
    subtotal_bruto = 0.0
    descuento_total = 0.0
    total = 0.0
    iva_por_tipo: dict = {}
    for it in items:
        cant = float(it.get("cantidad", 1) or 1)
        precio = float(it.get("precio", 0) or 0)
        sub = float(it.get("subtotal", cant * precio) or 0)
        bruto = round(cant * precio, 2)
        subtotal_bruto += bruto
        descuento_total += round(bruto - sub, 2)
        total += sub
        r = float(it.get("iva", 21) or 0)
        base = sub / (1 + r / 100) if r else sub
        iva_por_tipo.setdefault(r, [0.0, 0.0, 0.0])
        iva_por_tipo[r][0] += base           # base
        iva_por_tipo[r][1] += (sub - base)   # cuota
        iva_por_tipo[r][2] += sub            # pvp
    total = round(total, 2) if items else float(pago.get("total", 0) or 0)
    subtotal_bruto = round(subtotal_bruto, 2)
    descuento_total = round(descuento_total, 2)
    base_total = round(sum(v[0] for v in iva_por_tipo.values()), 2)
    iva_total = round(sum(v[1] for v in iva_por_tipo.values()), 2)

    # Forma de pago legible
    fp_raw = str(pago.get("forma_pago", "")).strip().lower()
    forma_pago = L(_FORMAS_PAGO[fp_raw], pago.get("forma_pago", "")) if fp_raw in _FORMAS_PAGO \
        else str(pago.get("forma_pago", ""))

    # ── Construcción por ELEMENTOS (para calcular el alto exacto) ─────────────
    W = 80 * mm
    MX = 5 * mm                  # margen lateral
    XL = MX                      # x izquierda
    XR = W - MX                  # x derecha
    CW = W - 2 * MX              # ancho útil
    elementos = []               # (alto, draw_fn(c, y))

    def add(h, fn):
        elementos.append((h, fn))

    def _wrap(texto, font, size, maxw):
        palabras = str(texto).split()
        lineas, cur = [], ""
        for w in palabras:
            prueba = (cur + " " + w).strip()
            if _strwidth(prueba, font, size) <= maxw:
                cur = prueba
            else:
                if cur:
                    lineas.append(cur)
                cur = w
        if cur:
            lineas.append(cur)
        return lineas or [""]

    # Necesitamos un canvas para medir; reportlab permite stringWidth sin canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth as _strwidth_rl

    def _strwidth(t, f, s):
        try:
            return _strwidth_rl(t, f, s)
        except Exception:
            return len(t) * s * 0.5

    def sep(h=8):
        def _f(c, y):
            c.setDash(1, 2); c.setLineWidth(0.5)
            c.line(XL, y - h / 2, XR, y - h / 2); c.setDash()
        add(h, _f)

    def linea_kv(k, v, font=None, size=8, bold_v=False):
        font = font or _FN
        def _f(c, y):
            c.setFont(font, size); c.drawString(XL, y - size, str(k))
            c.setFont(_FB if bold_v else font, size); c.drawRightString(XR, y - size, str(v))
        add(size + 4, _f)

    def texto(t, font=None, size=8, center=False, color=(0, 0, 0), gap=3):
        font = font or _FN
        for ln in _wrap(t, font, size, CW):
            def _f(c, y, _ln=ln, _f2=font, _s=size, _cen=center, _col=color):
                c.setFillColorRGB(*_col); c.setFont(_f2, _s)
                if _cen:
                    c.drawCentredString(W / 2, y - _s, _ln)
                else:
                    c.drawString(XL, y - _s, _ln)
                c.setFillColorRGB(0, 0, 0)
            add(size + gap, _f)

    def espacio(h):
        add(h, lambda c, y: None)

    # 1) LOGO
    logo = datos.get("logo")
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo)
            iw, ih = ir.getSize()
            lw = 38 * mm
            lh = lw * (ih / iw) if iw else 18 * mm
            lh = min(lh, 22 * mm)
            lw = lh * (iw / ih) if ih else lw
            def _f(c, y, _ir=ir, _lw=lw, _lh=lh):
                c.drawImage(_ir, (W - _lw) / 2, y - _lh, _lw, _lh,
                            preserveAspectRatio=True, mask="auto")
            add(lh + 4, _f)
        except Exception as e:
            logger.warning("No se pudo dibujar el logo del ticket: %s", e)

    # 2) CABECERA FISCAL (si no hay logo, el nombre comercial es el fallback)
    nombre = (emp.get("nombre_comercial") or emp.get("nombre")
              or emp.get("razon_social") or L("title", "SMART MANAGER"))
    texto(nombre, _FB, 11, center=True)
    dir_completa = emp.get("direccion_completa") or emp.get("direccion") or ""
    for ln in [
        (f"{L('cif', 'CIF')}: {emp.get('cif')}" if emp.get("cif") else ""),
        dir_completa,
        emp.get("pais") or "",
        (f"{L('phone', 'Tel')}: {emp.get('telefono')}" if emp.get("telefono") else ""),
        emp.get("email") or "",
        emp.get("web") or "",
    ]:
        if ln:
            texto(ln, _FN, 7, center=True, gap=2)

    sep()

    # 3) DATOS DE OPERACIÓN
    if tienda.get("nombre"):
        cod = f"  ({tienda.get('codigo')})" if tienda.get("codigo") else ""
        texto(f"{tienda.get('nombre')}{cod}", _FB, 8, center=True)
    if oper.get("ticket_num"):
        linea_kv(L("ticket_no", "Ticket"), oper.get("ticket_num"))
    if oper.get("venta_id") is not None:
        linea_kv(L("sale", "Venta"), oper.get("venta_id"))
    cl = " · ".join(str(x) for x in [oper.get("caja"), oper.get("terminal")] if x)
    if cl:
        linea_kv(L("register", "Caja"), cl)
    if oper.get("empleado") not in (None, ""):
        linea_kv(L("employee", "Empleado"), oper.get("empleado"))
    if oper.get("fecha"):
        linea_kv(L("date", "Fecha"), oper.get("fecha"))

    sep()

    # 4) CABECERA DE COLUMNAS + LÍNEAS
    def _f_head(c, y):
        c.setFont(_FB, 7)
        c.drawString(XL, y - 7, L("col_desc", "DESCRIPCIÓN"))
        c.drawRightString(XR, y - 7, L("col_amount", "IMPORTE"))
    add(11, _f_head)

    for i, it in enumerate(items):
        nombre_it = nombres_tr[i] if i < len(nombres_tr) else it.get("nombre", "")
        cant = float(it.get("cantidad", 1) or 1)
        precio = float(it.get("precio", 0) or 0)
        sub = float(it.get("subtotal", cant * precio) or 0)
        bruto = round(cant * precio, 2)
        dto = float(it.get("descuento_pct", 0) or 0)
        es_granel = it.get("granel") or it.get("modo_venta") == "PESO" or it.get("peso")

        # Nombre (con importe bruto a la derecha)
        for j, ln in enumerate(_wrap(nombre_it, _FB, 8, CW - 22 * mm)):
            def _f(c, y, _ln=ln, _j=j, _bruto=bruto):
                c.setFont(_FB, 8); c.drawString(XL, y - 8, _ln)
                if _j == 0:
                    c.setFont(_FN, 8); c.drawRightString(XR, y - 8, M(_bruto))
            add(11, _f)
        # Detalle cantidad × precio (o peso × precio/kg para granel)
        if es_granel and it.get("peso"):
            det = f"{float(it['peso']):.3f} {it.get('unidad','kg')} × {M(it.get('precio_kg', 0))}/{it.get('unidad','kg')}"
        else:
            cant_txt = (f"{cant:g}")
            det = f"{cant_txt} × {M(precio)}"
        def _fd(c, y, _det=det):
            c.setFont(_FN, 7); c.setFillColorRGB(0.35, 0.35, 0.35)
            c.drawString(XL + 3 * mm, y - 7, _det); c.setFillColorRGB(0, 0, 0)
        add(10, _fd)
        # Descuento de línea
        if dto > 0:
            desc_imp = round(bruto - sub, 2)
            def _fdto(c, y, _dto=dto, _imp=desc_imp):
                c.setFont(_FN, 7); c.setFillColorRGB(0.0, 0.45, 0.30)
                c.drawString(XL + 3 * mm, y - 7, f"{L('discount', 'Descuento')} {_dto:g}%")
                c.drawRightString(XR, y - 7, f"-{M(_imp)}")
                c.setFillColorRGB(0, 0, 0)
            add(10, _fdto)

    sep()

    # 5) SUBTOTAL / DESCUENTOS / BASE
    if descuento_total > 0.005:
        linea_kv(L("subtotal_products", "Subtotal productos"), M(subtotal_bruto))
        linea_kv(L("discounts", "Descuentos"), f"-{M(descuento_total)}")
    sep()

    # 6) DESGLOSE FISCAL — al final, nunca por línea.
    #    Un solo tipo de IVA → bloque simple (Base imponible / IVA (r%)).
    #    Varios tipos → tabla por tipo (preparado para fiscalidad multi-tipo).
    if len(iva_por_tipo) <= 1:
        r = next(iter(iva_por_tipo), 0.0)
        linea_kv(L("vat_base_total", "Base imponible"), M(base_total))
        linea_kv(f"{L('vat', 'IVA')} ({r:g}%)", M(iva_total))
    else:
        def _f_ivah(c, y):
            c.setFont(_FB, 7)
            c.drawString(XL, y - 7, L("vat", "IVA"))
            c.drawString(XL + 16 * mm, y - 7, L("base", "Base"))
            c.drawString(XL + 36 * mm, y - 7, L("vat_fee", "Cuota"))
            c.drawRightString(XR, y - 7, L("col_amount", "Importe"))
        add(11, _f_ivah)
        for r in sorted(iva_por_tipo.keys()):
            base, cuota, pvp = iva_por_tipo[r]
            def _f(c, y, _r=r, _b=base, _c=cuota, _p=pvp):
                c.setFont(_FN, 7)
                c.drawString(XL, y - 7, f"{_r:g}%")
                c.drawString(XL + 16 * mm, y - 7, M(round(_b, 2)))
                c.drawString(XL + 36 * mm, y - 7, M(round(_c, 2)))
                c.drawRightString(XR, y - 7, M(round(_p, 2)))
            add(10, _f)
        linea_kv(L("vat_base_total", "Base imponible"), M(base_total), size=7)
        linea_kv(L("vat_total", "Total IVA"), M(iva_total), size=7)

    sep()

    # 7) TOTAL DESTACADO
    def _f_total(c, y):
        c.setFont(_FB, 8); c.drawString(XL, y - 8, "")
        c.setLineWidth(1.0); c.rect(XL, y - 24, CW, 22, stroke=1, fill=0)
        c.setFont(_FB, 9); c.drawString(XL + 3 * mm, y - 17, L("total_to_pay", "TOTAL A PAGAR"))
        c.setFont(_FB, 14); c.drawRightString(XR - 3 * mm, y - 18, M(total))
    add(28, _f_total)
    espacio(4)

    # 8) DESGLOSE DE PAGO
    if forma_pago:
        linea_kv(L("payment", "Forma de pago"), forma_pago, bold_v=True)
    cambio = pago.get("cambio") or 0.0
    if fp_raw == "mixto":
        if pago.get("efectivo"):
            linea_kv(L("pay_cash", "Efectivo"), M(pago.get("efectivo")), size=7)
        if pago.get("tarjeta"):
            linea_kv(L("card_amount", "Tarjeta"), M(pago.get("tarjeta")), size=7)
        if cambio > 0.005:
            linea_kv(L("change", "Cambio"), M(cambio), size=7)
    elif fp_raw == "tarjeta":
        if pago.get("tarjeta_info"):
            texto(pago.get("tarjeta_info"), _FN, 7, gap=2)
    else:  # efectivo (u otros)
        if pago.get("entregado") is not None:
            linea_kv(L("delivered", "Entregado"), M(pago.get("entregado")), size=7)
        if cambio > 0.005:
            linea_kv(L("change", "Cambio"), M(cambio), size=7)

    sep()

    # 9) CÓDIGO DE BARRAS + QR
    ticket_num = oper.get("ticket_num") or str(oper.get("venta_id") or "")
    if ticket_num:
        ir_bc, ratio = _ticket_imagen_codigo("bc", ticket_num)
        if ir_bc is not None:
            bw = 55 * mm
            bh = max(10 * mm, min(16 * mm, bw * ratio))
            def _f(c, y, _ir=ir_bc, _bw=bw, _bh=bh):
                c.drawImage(_ir, (W - _bw) / 2, y - _bh, _bw, _bh, preserveAspectRatio=True, mask="auto")
            add(bh + 4, _f)
    qr_payload = datos.get("qr")
    if qr_payload:
        ir_qr, _ = _ticket_imagen_codigo("qr", qr_payload)
        if ir_qr is not None:
            qs = 22 * mm
            def _f(c, y, _ir=ir_qr, _qs=qs):
                c.drawImage(_ir, (W - _qs) / 2, y - _qs, _qs, _qs, preserveAspectRatio=True, mask="auto")
            add(qs + 4, _f)

    sep()

    # 10) POLÍTICA DE DEVOLUCIÓN
    dias = cfg.get("devol_dias", 30)
    texto(L("return_policy", "Dispone de {d} días para devoluciones presentando este ticket.").format(d=dias),
          _FN, 7, center=True, gap=2)
    espacio(2)

    # 11) MENSAJE DE DESPEDIDA + TEXTO LEGAL
    msg = cfg.get("mensaje_despedida") or L("thanks", "¡Gracias por su compra!")
    texto(msg, _FB, 9, center=True)
    if cfg.get("texto_legal"):
        espacio(2)
        for ln in str(cfg.get("texto_legal")).splitlines():
            texto(ln, _FN, 6, center=True, gap=1)

    # 12) TRAZABILIDAD (discreta)
    espacio(4)
    traza = []
    if oper.get("venta_id") is not None:
        traza.append(f"REF {oper.get('venta_id')}")
    if datos.get("hash"):
        traza.append(str(datos.get("hash"))[:16])
    if traza:
        texto("  ·  ".join(traza), _FN, 5, center=True, color=(0.5, 0.5, 0.5), gap=1)

    # ── Render ───────────────────────────────────────────────────────────────
    top_pad = 6 * mm
    bot_pad = 6 * mm
    alto = top_pad + bot_pad + sum(h for h, _ in elementos)
    c = canvas.Canvas(archivo, pagesize=(W, alto))
    y = alto - top_pad
    for h, fn in elementos:
        fn(c, y)
        y -= h
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
