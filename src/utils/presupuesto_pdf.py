"""
Generación del PDF de un presupuesto de cliente y su alta en el Centro Documental.

Reutiliza los helpers de `factura_pdf.py` (emisor, logo corporativo, fuente Unicode, bloque de
dirección) — mismo aspecto visual y mismo pie con el branding de Smart Manager, sin duplicar
lógica de resolución de datos de empresa. Degrada con elegancia si falta algún dato.
"""
import datetime as _dt
import logging
import os

logger = logging.getLogger(__name__)


def _dir_presupuestos() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "documentos", "Presupuestos")
    os.makedirs(base, exist_ok=True)
    return base


def ruta_presupuesto(numero) -> str:
    """Ruta esperada del PDF de un presupuesto por su número (PRE######)."""
    return os.path.join(_dir_presupuestos(), f"{numero}.pdf")


def _fecha_base(presupuesto: dict) -> _dt.date:
    fecha = presupuesto.get("fecha")
    try:
        if isinstance(fecha, _dt.datetime):
            return fecha.date()
        if isinstance(fecha, _dt.date):
            return fecha
        if fecha:
            return _dt.datetime.fromisoformat(str(fecha)).date()
    except Exception:
        pass
    return _dt.date.today()


def generar_pdf_presupuesto(presupuesto: dict, cliente: dict, *, id_empresa=None,
                            validez_dias: int = 30, emisor: dict | None = None) -> str | None:
    """Genera el PDF del presupuesto y lo devuelve (ruta). `presupuesto` debe traer numero, fecha,
    estado, total, observaciones, lineas=[{codigo_articulo, descripcion, cantidad,
    precio_unitario, subtotal}] (shape de `src.db.ventas_comercial.obtener_presupuesto`)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from src.utils import divisas
        from src.utils.factura_pdf import _bloque_direccion, _logo_corp, _registrar_fuente
        from src.utils.factura_pdf import emisor as _emisor_actual
    except Exception as e:
        logger.error("generar_pdf_presupuesto: dependencias no disponibles: %s", e)
        return None

    numero = presupuesto.get("numero") or f"PRE{int(presupuesto.get('id') or 0):06d}"
    ruta = os.path.join(_dir_presupuestos(), f"{numero}.pdf")
    em = emisor or _emisor_actual()
    fecha_base = _fecha_base(presupuesto)
    validez_dias = int(validez_dias or 30)
    fecha_validez = (fecha_base + _dt.timedelta(days=validez_dias)).isoformat()

    reg, bold = _registrar_fuente()
    styles = getSampleStyleSheet()
    h = styles["Heading1"]; sm = styles["Normal"].clone("sm"); sm.fontSize = 8
    h.fontName = bold; sm.fontName = reg
    try:
        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=18 * mm, bottomMargin=18 * mm,
                                title=f"Presupuesto {numero}")
        story = []

        # Cabecera: título + logo corporativo a la derecha (idéntico patrón que facturas).
        titulo_par = Paragraph("PRESUPUESTO", h)
        _logo = _logo_corp()
        if _logo is not None:
            cab_top = Table([[titulo_par, _logo]], colWidths=[120 * mm, 54 * mm])
            cab_top.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(cab_top)
        else:
            story.append(titulo_par)

        estado = str(presupuesto.get("estado") or "borrador").upper()
        izq_info = [f"Nº presupuesto:  {numero}", f"Fecha:  {fecha_base.isoformat()}",
                    f"Estado:  {estado}"]
        der_info = [f"Válido hasta:  {fecha_validez}", "", ""]
        _COLW = [92 * mm, 80 * mm]
        info = Table(list(zip(izq_info, der_info)), colWidths=_COLW)
        info.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), reg),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(Spacer(1, 6))
        story.append(info)
        story.append(Spacer(1, 12))

        emisor_html = (f"<b>Emisor:</b> {em['nombre']}<br/>"
                       + (f"NIF: {em['nif']}<br/>" if em['nif'] else "")
                       + _bloque_direccion(em)
                       + (f"Tel: {em['telefono']}<br/>" if em['telefono'] else "")
                       + (f"{em['email']}" if em['email'] else ""))
        receptor_html = (f"<b>Cliente:</b> {cliente.get('nombre', '')}<br/>"
                         + (f"NIF: {cliente.get('nif')}<br/>" if cliente.get('nif') else "")
                         + _bloque_direccion(cliente)
                         + (f"Tel: {cliente.get('telefono')}<br/>" if cliente.get('telefono') else "")
                         + (f"{cliente.get('email')}" if cliente.get('email') else ""))
        cab = Table([[Paragraph(emisor_html, sm), Paragraph(receptor_html, sm)]], colWidths=_COLW)
        cab.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(cab)
        story.append(Spacer(1, 12))

        filas = [["Descripción", "Cant.", "P. Unit.", "Subtotal"]]
        for ln in (presupuesto.get("lineas") or []):
            cant = ln.get("cantidad") or 0
            try:
                cant_s = str(int(cant))
            except Exception:
                cant_s = str(cant)
            filas.append([
                str(ln.get("descripcion") or ln.get("codigo_articulo") or ""),
                cant_s,
                divisas.formatear(ln.get("precio_unitario")),
                divisas.formatear(ln.get("subtotal")),
            ])
        tabla = Table(filas, colWidths=[90 * mm, 20 * mm, 30 * mm, 34 * mm])
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E1117")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#00B488")),
            ("FONTNAME", (0, 0), (-1, -1), reg),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#888888")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(tabla)
        story.append(Spacer(1, 10))

        # Total — sin desglose de IVA: `ventas_presupuestos` no tiene columnas fiscales, no se
        # inventan aquí (a diferencia de facturas, que sí desglosan impuestos reales).
        total = divisas.formatear(presupuesto.get("total"))
        tot = Table([["TOTAL", total]], colWidths=[120 * mm, 54 * mm])
        tot.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, -1), bold),
            ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black),
        ]))
        story.append(tot)

        story.append(Spacer(1, 10))
        cond = styles["Normal"].clone("cond"); cond.fontName = reg; cond.fontSize = 8
        cond.textColor = colors.HexColor("#444444")
        cond_txt = ("Presupuesto sin compromiso, sujeto a la disponibilidad de stock en el "
                    f"momento del pedido. Validez de la oferta: {validez_dias} días desde la "
                    "fecha de emisión.")
        if presupuesto.get("observaciones"):
            cond_txt = f"{presupuesto.get('observaciones')}<br/>{cond_txt}"
        story.append(Paragraph(cond_txt, cond))

        # Pie documental — mismo branding gris tenue que ya usan las facturas.
        story.append(Spacer(1, 18))
        pie = styles["Normal"].clone("pie"); pie.fontName = reg; pie.fontSize = 7
        pie.textColor = colors.HexColor("#888888")
        story.append(Paragraph(
            f"Documento generado por Smart Manager · {numero} · {fecha_base.isoformat()}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_presupuesto(%s): %s", numero, e)
        return None


def generar_y_registrar_presupuesto(presupuesto: dict, cliente: dict, *, id_empresa=None,
                                    validez_dias: int = 30) -> str | None:
    """Genera el PDF del presupuesto y lo da de alta en el Centro Documental (tipo
    'presupuesto'). Devuelve la ruta, o None si falló."""
    ruta = generar_pdf_presupuesto(presupuesto, cliente, id_empresa=id_empresa,
                                   validez_dias=validez_dias)
    if not ruta:
        return None
    try:
        from src.db import documentos
        documentos.registrar_documento(
            ruta, tipo="presupuesto", nombre=os.path.basename(ruta),
            referencia=(presupuesto or {}).get("numero"), cliente=(cliente or {}).get("nombre"),
            importe=(presupuesto or {}).get("total"), estado="generado", id_empresa=id_empresa)
    except Exception as e:
        logger.error("registrar presupuesto en documental: %s", e)
    return ruta
