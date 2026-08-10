"""
Generación del PDF de una factura comercial de cliente y su alta en el Centro Documental.

Reutiliza la infraestructura existente: datos de empresa (emisor), divisas (formato),
fiscalidad (desglose IVA) y src.db.documentos (registro centralizado). Degrada con
elegancia si falta algún dato.
"""
import datetime as _dt
import logging
import os

logger = logging.getLogger(__name__)


def _dir_facturas() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "documentos", "Facturas")
    os.makedirs(base, exist_ok=True)
    return base


def ruta_factura(numero) -> str:
    """Ruta esperada del PDF de una factura por su número (FC######)."""
    return os.path.join(_dir_facturas(), f"{numero}.pdf")


def emisor() -> dict:
    """Datos fiscales actuales del emisor (público, para congelar en el snapshot)."""
    return _emisor()


def _emisor() -> dict:
    """Datos fiscales del emisor desde 'Datos corporativos' (tabla empresas)."""
    datos = {"nombre": "SMART MANAGER", "nif": "", "direccion": "", "email": "",
             "telefono": "", "cp": "", "municipio": "", "provincia": "", "pais": ""}
    try:
        from src.db.empresa import obtener_empresa
        e = obtener_empresa() or {}
        datos["nombre"] = e.get("razon_social") or e.get("nombre_empresa") or datos["nombre"]
        datos["nif"] = e.get("cif_nif") or ""
        datos["direccion"] = e.get("direccion_fiscal") or ""
        datos["email"] = e.get("email_principal") or ""
        datos["telefono"] = e.get("telefono") or ""
        datos["cp"] = e.get("cp") or ""
        datos["municipio"] = e.get("municipio") or ""
        datos["provincia"] = e.get("provincia") or ""
        datos["pais"] = e.get("pais") or ""
    except Exception:
        pass
    if not datos["nombre"] or not datos["email"]:
        try:
            from src.db.conexion import obtener_configuracion
            cfg = obtener_configuracion() or {}
            datos["nombre"] = datos["nombre"] or cfg.get("nombre_empresa") or "SMART MANAGER"
            datos["email"] = datos["email"] or cfg.get("email") or ""
        except Exception:
            pass
    return datos


def _bloque_direccion(d: dict) -> str:
    """Línea(s) de domicilio: 'CP municipio (provincia)' + país."""
    loc = " ".join(p for p in [d.get("cp"), d.get("municipio") or d.get("poblacion")] if p)
    if d.get("provincia"):
        loc = (loc + f" ({d.get('provincia')})").strip()
    out = ""
    if d.get("direccion"):
        out += f"{d.get('direccion')}<br/>"
    if loc.strip():
        out += f"{loc}<br/>"
    if d.get("pais"):
        out += f"{d.get('pais')}<br/>"
    return out


_FUENTE_CACHE = None


def _registrar_fuente():
    """Registra una fuente TTF Unicode (regular, bold) para que el PDF muestre símbolos de
    divisa (₩, €, ¥…) y otros glifos. Devuelve (regular, bold). Fallback: Helvetica."""
    global _FUENTE_CACHE
    if _FUENTE_CACHE is not None:
        return _FUENTE_CACHE
    regular, bold = "Helvetica", "Helvetica-Bold"
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        candidatos = [
            ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
            ("/System/Library/Fonts/Supplemental/Arial.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ]
        for reg, bd in candidatos:
            if os.path.exists(reg):
                pdfmetrics.registerFont(TTFont("SMUni", reg))
                regular = "SMUni"
                if os.path.exists(bd):
                    pdfmetrics.registerFont(TTFont("SMUni-Bold", bd))
                    bold = "SMUni-Bold"
                else:
                    bold = "SMUni"
                break
    except Exception as e:
        logger.debug("registrar fuente PDF: %s", e)
    _FUENTE_CACHE = (regular, bold)
    return _FUENTE_CACHE


def _fmt_cantidad(it: dict) -> str:
    """Formatea la cantidad de una línea: entero sin decimales, peso con hasta 3 decimales
    (sin ceros sobrantes) y sufijo ' kg' en líneas a granel."""
    try:
        c = float(it.get("cantidad") or 0)
        s = str(int(c)) if c == int(c) else f"{c:.3f}".rstrip("0").rstrip(".")
    except Exception:
        s = str(it.get("cantidad") or 0)
    if str(it.get("modo_venta") or "").upper() in ("PESO", "GRANEL"):
        s += " kg"
    return s


def _logo_corp(alto_mm=16):
    """Logo corporativo (documentos/logo_corporativo.png) como flowable Image para la
    esquina superior derecha de la factura. None si no se ha subido ninguno."""
    try:
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "documentos", "logo_corporativo.png")
        if not os.path.exists(p):
            return None
        iw, ih = ImageReader(p).getSize()
        ratio = (iw / ih) if ih else 1
        alto = alto_mm * mm
        return Image(p, width=alto * ratio, height=alto)
    except Exception as e:
        logger.debug("logo corporativo factura: %s", e)
        return None


def _qr_imagen(payload, lado_mm=24):
    """Devuelve un flowable Image con el QR del `payload` (reusa qrcode). None si no procede."""
    if not payload:
        return None
    try:
        from io import BytesIO

        import qrcode
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
        buf = BytesIO()
        qrcode.make(payload).save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=lado_mm * mm, height=lado_mm * mm)
    except Exception as e:
        logger.debug("QR factura: %s", e)
        return None


def generar_pdf_factura(factura: dict, cliente: dict, items: list, *, id_empresa=None,
                        impuestos: list | None = None, fiscal: dict | None = None,
                        emisor: dict | None = None, moneda: str | None = None) -> str | None:
    """Genera el PDF de la factura y lo devuelve (ruta). `factura` debe traer numero,
    base, iva, total, fecha_emision; `items` = [{nombre, cantidad, precio_unitario, subtotal}]."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

        from src.utils import divisas
    except Exception as e:
        logger.error("generar_pdf_factura: dependencias no disponibles: %s", e)
        return None

    numero = factura.get("numero") or f"FC{int(factura.get('id_factura') or 0):06d}"
    ruta = os.path.join(_dir_facturas(), f"{numero}.pdf")
    em = emisor or _emisor()   # emisor congelado del snapshot, o datos vivos de la empresa
    fecha = factura.get("fecha_emision") or _dt.date.today().isoformat()

    reg, bold = _registrar_fuente()
    styles = getSampleStyleSheet()
    h = styles["Heading1"]; n = styles["Normal"]; sm = styles["Normal"].clone("sm"); sm.fontSize = 8
    h.fontName = bold; n.fontName = reg; sm.fontName = reg
    try:
        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=18 * mm, bottomMargin=18 * mm, title=f"Factura {numero}")
        story = []
        # Cabecera: título según el TIPO de documento + logo corporativo a la derecha.
        _tipo = factura.get("tipo_documento") or "factura"
        try:
            from src.services.facturacion import tipos_documento as _TD
            _titulo = "FACTURA PAGADA" if _tipo == "factura" else (_TD.regla(_tipo).get("etiqueta") or "FACTURA")
            _marca = _TD.marca(_tipo)
        except Exception:
            _titulo, _marca = "FACTURA PAGADA", None
        titulo_par = Paragraph(_titulo, h)
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
        if _marca:   # marca visible (p. ej. PROFORMA: documento sin valor fiscal)
            mk = styles["Normal"].clone("mk"); mk.fontName = bold; mk.fontSize = 11
            mk.textColor = colors.HexColor("#B00020")
            story.append(Paragraph(f"— {_marca} · documento sin valor fiscal —", mk))
        # Datos de la factura: nº, fecha, estado | (serie), forma de pago. Serie solo si existe.
        estado = str(factura.get("estado") or "borrador").upper()
        forma = str(factura.get("forma_pago") or "—").capitalize()
        izq_info = [f"Nº factura:  {numero}", f"Fecha:  {fecha}", f"Estado:  {estado}"]
        der_info = [f"Forma de pago:  {forma}"]
        if factura.get("serie"):
            der_info.insert(0, f"Serie:  {factura.get('serie')}")
        while len(der_info) < len(izq_info):
            der_info.append("")
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
        receptor_html = (f"<b>Cliente:</b> {cliente.get('nombre','')}<br/>"
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

        filas = [["Artículo", "Cant.", "P. Unit.", "Subtotal"]]
        for it in (items or []):
            filas.append([
                str(it.get("nombre") or it.get("codigo_articulo") or ""),
                _fmt_cantidad(it),
                divisas.formatear(it.get("precio_unitario"), code=moneda),
                divisas.formatear(it.get("subtotal"), code=moneda),
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

        def _pct(v):
            v = float(v or 0)
            return f"{v:.0f}" if abs(v - round(v)) < 0.005 else f"{v:.2f}"
        base = divisas.formatear(factura.get("base"), code=moneda)
        total = divisas.formatear(factura.get("total"), code=moneda)
        # Totales: IVA por tipo + recargo de equivalencia + retención IRPF (FASE 3.2).
        filas_tot = [["Base imponible", base]]
        for t in (impuestos or []):
            tipo = float(t.get("tipo_iva") or 0)
            if tipo > 0:
                filas_tot.append([f"IVA {_pct(tipo)}%", divisas.formatear(t.get("cuota"), code=moneda)])
            rec = float(t.get("cuota_recargo") or 0)
            if rec:
                filas_tot.append([f"Recargo equiv. {_pct(t.get('tipo_recargo'))}%",
                                  divisas.formatear(rec, code=moneda)])
        if not impuestos:
            filas_tot.append(["IVA", divisas.formatear(factura.get("iva"), code=moneda)])
        _ret = float(factura.get("retencion_importe") or 0)
        if _ret:
            filas_tot.append([f"Retención IRPF {_pct(factura.get('retencion_pct'))}%",
                              "-" + divisas.formatear(_ret, code=moneda)])
        filas_tot.append(["TOTAL", total])
        _last = len(filas_tot) - 1
        tot = Table(filas_tot, colWidths=[120 * mm, 54 * mm])
        tot.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, -1), reg),
            ("FONTNAME", (0, _last), (-1, _last), bold),
            ("LINEABOVE", (0, _last), (-1, _last), 0.6, colors.black),
        ]))
        story.append(tot)

        # Leyenda legal del régimen (ISP / intracomunitaria / exento), si aplica.
        if factura.get("leyenda_fiscal"):
            story.append(Spacer(1, 8))
            ley = styles["Normal"].clone("ley"); ley.fontName = reg; ley.fontSize = 8
            ley.textColor = colors.HexColor("#444444")
            story.append(Paragraph(str(factura.get("leyenda_fiscal")), ley))

        # Bloque fiscal (Verifactu): registro fiscal + QR de cotejo + leyenda legal + CSV.
        # Solo aparece si la venta tiene registro fiscal (módulo activo); si no, nada.
        if fiscal:
            story.append(Spacer(1, 14))
            txt = ""
            if fiscal.get("numserie"):
                txt += f"<b>Registro fiscal:</b> {fiscal.get('numserie')}<br/>"
            if fiscal.get("leyenda"):
                txt += f"{fiscal.get('leyenda')}<br/>"
            if fiscal.get("csv"):
                txt += f"CSV: {fiscal.get('csv')}"
            parr = Paragraph(txt, sm) if txt else None
            qrimg = _qr_imagen(fiscal.get("qr"))
            if qrimg is not None and parr is not None:
                fb = Table([[qrimg, parr]], colWidths=[28 * mm, _COLW[0] + _COLW[1] - 28 * mm])
                fb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                story.append(fb)
            elif qrimg is not None:
                story.append(qrimg)
            elif parr is not None:
                story.append(parr)
        else:
            # QR INTERNO documental (prioridad 2): solo si NO hay QR Verifactu. Para
            # verificación/consulta interna (factura/auditoría/historial/hash). No fiscal.
            import hashlib
            payload_int = (f"SMART|{factura.get('numero')}|{fecha}|"
                           f"{factura.get('total')}|{moneda or ''}")
            h_int = hashlib.sha256(payload_int.encode("utf-8")).hexdigest()[:16]
            qint = _qr_imagen(payload_int + "|" + h_int, lado_mm=20)
            if qint is not None:
                story.append(Spacer(1, 14))
                cap = styles["Normal"].clone("qint"); cap.fontName = reg; cap.fontSize = 7
                cap.textColor = colors.HexColor("#888888")
                fb = Table([[qint, Paragraph(f"Verificación interna<br/>{h_int}", cap)]],
                           colWidths=[24 * mm, _COLW[0] + _COLW[1] - 24 * mm])
                fb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                story.append(fb)
        # Pie documental (trazabilidad).
        story.append(Spacer(1, 18))
        pie = styles["Normal"].clone("pie"); pie.fontName = reg; pie.fontSize = 7
        pie.textColor = colors.HexColor("#888888")
        story.append(Paragraph(
            f"Documento generado por Smart Manager · {numero} · {fecha}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_factura(%s): %s", numero, e)
        return None


def construir_snapshot(factura: dict, cliente: dict, items: list, *, impuestos=None,
                       fiscal=None, emisor=None, moneda=None) -> dict:
    """Congela TODO lo necesario para reproducir el documento idéntico en el futuro
    (emisor, receptor, líneas, impuestos, totales, fiscal y moneda). Inmutable: el PDF
    se regenera SIEMPRE desde aquí, aunque cambien después los datos de empresa/cliente."""
    try:
        from src.utils import divisas
        moneda = moneda or divisas.divisa_actual()
    except Exception:
        pass
    return {
        "version": 1,
        "emisor": emisor or _emisor(),
        "cliente": {k: cliente.get(k) for k in (
            "nombre", "nif", "telefono", "email", "direccion", "domicilio",
            "cp", "poblacion", "municipio", "provincia", "pais")} if cliente else {},
        "factura": {k: factura.get(k) for k in (
            "numero", "serie", "numero_serie", "estado", "tipo_documento",
            "fecha_emision", "forma_pago", "base", "iva", "total",
            "regimen_fiscal", "cuota_recargo", "retencion_pct", "retencion_importe",
            "leyenda_fiscal")},
        "items": [{"nombre": it.get("nombre") or it.get("descripcion"),
                   "codigo_articulo": it.get("codigo_articulo") or it.get("codigo"),
                   "cantidad": it.get("cantidad"),
                   "precio_unitario": it.get("precio_unitario"),
                   "subtotal": it.get("subtotal"),
                   "iva": it.get("iva"),
                   "modo_venta": it.get("modo_venta")} for it in (items or [])],
        "impuestos": [{"tipo_iva": i.get("tipo_iva"), "base": i.get("base"),
                       "cuota": i.get("cuota"), "total": i.get("total")}
                      for i in (impuestos or [])],
        "fiscal": fiscal or None,
        "moneda": moneda,
    }


def generar_pdf_desde_snapshot(snap: dict) -> str | None:
    """Regenera el PDF EXACTO desde un snapshot congelado (emisor/cliente/líneas/moneda)."""
    if not snap:
        return None
    cli = dict(snap.get("cliente") or {})
    if cli.get("domicilio") and not cli.get("direccion"):
        cli["direccion"] = cli.get("domicilio")
    return generar_pdf_factura(
        snap.get("factura") or {}, cli, snap.get("items") or [],
        impuestos=snap.get("impuestos"), fiscal=snap.get("fiscal"),
        emisor=snap.get("emisor"), moneda=snap.get("moneda"))


def generar_y_registrar(factura: dict, cliente: dict, items: list, *, id_empresa=None,
                        impuestos: list | None = None, fiscal: dict | None = None,
                        emisor: dict | None = None, snapshot: dict | None = None) -> str | None:
    """Genera el PDF y lo da de alta en el Centro Documental (tipo 'factura'). Si se pasa
    `snapshot`, el PDF se genera DESDE el snapshot congelado (reproducible). Devuelve la ruta."""
    if snapshot:
        ruta = generar_pdf_desde_snapshot(snapshot)
        factura = snapshot.get("factura") or factura
        cliente = snapshot.get("cliente") or cliente
    else:
        ruta = generar_pdf_factura(factura, cliente, items, id_empresa=id_empresa,
                                   impuestos=impuestos, fiscal=fiscal, emisor=emisor)
    if not ruta:
        return None
    try:
        from src.db import documentos
        documentos.registrar_documento(
            ruta, tipo="factura", nombre=os.path.basename(ruta),
            referencia=(factura or {}).get("numero"), cliente=(cliente or {}).get("nombre"),
            importe=(factura or {}).get("total"), estado="generado", id_empresa=id_empresa)
    except Exception as e:
        logger.error("registrar factura en documental: %s", e)
    return ruta
