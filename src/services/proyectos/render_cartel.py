"""
Renderizador puro de carteles/folletos publicitarios (Proyectos · "Carteles/Folletos
publicitarios"). Lee el MISMO modelo de contenido que edita el canvas interactivo
(`gui/proyectos_carteles_gui.py`, JSON guardado en `proyecto_carteles.contenido_json`) y lo
convierte en píxeles (PNG/JPG, revisión digital) o en un PDF listo para imprenta (reportlab, con
sangrado real y marcas de corte/plegado) — sin Qt, 100% testable sin QApplication. La miniatura de
la galería y la exportación rápida reutilizan `render_png`; la exportación profesional usa
`render_pdf`.

Modelo de contenido (`doc`):
    {"ancho_mm": float, "alto_mm": float, "modo": None|"diptico"|"triptico",
     "fondo_color": "#RRGGBB",
     "elementos": [
        {"tipo":"texto", "x","y","w","h" (mm), "texto", "fuente":"regular"|"negrita",
         "tamano_pt", "color":"#RRGGBB", "alineacion":"izquierda"|"centro"|"derecha",
         "interlineado", "z"},
        {"tipo":"imagen", "x","y","w","h", "ruta", "z"},
        {"tipo":"qr", "x","y","w","h", "payload", "z"},
        {"tipo":"forma", "forma":"rectangulo"|"circulo"|"linea", "x","y","w","h",
         "color":"#RRGGBB", "relleno": bool, "grosor_mm", "z"},
     ]}
Todas las coordenadas/tamaños están en mm, origen arriba-izquierda, sobre el tamaño FINAL de
corte (sin sangrado) — el sangrado es puramente una ampliación en el momento de exportar a PDF.
"""

import io
import logging
import os

logger = logging.getLogger("proyectos.render_cartel")

MM_POR_PULGADA = 25.4
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _candidatos_ttf(negrita: bool):
    if os.name == "nt":
        return ["C:/Windows/Fonts/arialbd.ttf" if negrita else "C:/Windows/Fonts/arial.ttf"]
    if os.path.exists("/usr/share/fonts/truetype/dejavu"):
        return ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrita
               else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    return ["/Library/Fonts/Arial Bold.ttf" if negrita else "/Library/Fonts/Arial.ttf",
           "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if negrita
           else "/System/Library/Fonts/Supplemental/Arial.ttf"]


def _hex_a_rgb(color):
    color = (color or "#000000").lstrip("#")
    if len(color) != 6:
        color = "000000"
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def _elementos_ordenados(doc):
    return sorted(doc.get("elementos") or [], key=lambda e: e.get("z", 0))


def _envolver_texto(texto, medir_ancho, ancho_max):
    """Reparte `texto` en líneas que no superen `ancho_max` (según `medir_ancho(linea) -> float`),
    partiendo por palabras. Nunca deja una palabra sola más ancha que el cuadro sin incluirla
    igualmente (mejor que desbordar en silencio)."""
    lineas, actual = [], ""
    for palabra in (texto or "").split():
        candidata = f"{actual} {palabra}".strip()
        if actual and medir_ancho(candidata) > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = candidata
    if actual:
        lineas.append(actual)
    return lineas or [""]


# ── PNG/JPG (Pillow) — revisión digital y miniaturas de galería ──────────────────────────────
def render_png(doc: dict, *, dpi=150) -> bytes:
    """Rasteriza `doc` a PNG en memoria, a `dpi`. Nunca lanza: ante cualquier elemento
    problemático (imagen que no existe, fuente no disponible…) lo omite y sigue con el resto —
    un cartel a medio terminar se ve a medio terminar, nunca un error que tira todo el render."""
    from PIL import Image, ImageDraw, ImageFont

    ancho_px = max(1, round(float(doc.get("ancho_mm") or 1) / MM_POR_PULGADA * dpi))
    alto_px = max(1, round(float(doc.get("alto_mm") or 1) / MM_POR_PULGADA * dpi))
    img = Image.new("RGB", (ancho_px, alto_px), _hex_a_rgb(doc.get("fondo_color") or "#FFFFFF"))
    draw = ImageDraw.Draw(img)

    def mm_px(v):
        return round(float(v or 0) / MM_POR_PULGADA * dpi)

    def _fuente_pil(negrita, tamano_pt):
        # tamano_pt (puntos, 1/72") -> píxeles a este DPI.
        tamano_px = max(6, round(tamano_pt / 72 * dpi))
        for ruta in _candidatos_ttf(negrita):
            try:
                if os.path.exists(ruta):
                    return ImageFont.truetype(ruta, tamano_px)
            except Exception:
                continue
        try:
            return ImageFont.load_default(size=tamano_px)
        except Exception:
            return ImageFont.load_default()

    for el in _elementos_ordenados(doc):
        try:
            tipo = el.get("tipo")
            x, y, w, h = mm_px(el.get("x")), mm_px(el.get("y")), mm_px(el.get("w")), mm_px(el.get("h"))
            if tipo == "texto":
                negrita = "negrita" in (el.get("fuente") or "")
                fuente = _fuente_pil(negrita, float(el.get("tamano_pt") or 14))
                color = _hex_a_rgb(el.get("color") or "#000000")
                interlineado = float(el.get("interlineado") or 1.2)
                lh = round(fuente.size * interlineado)

                def medir(s, _f=fuente):
                    return draw.textlength(s, font=_f)
                lineas = _envolver_texto(el.get("texto") or "", medir, max(w, 1))
                cy = y
                alineacion = el.get("alineacion") or "izquierda"
                for linea in lineas:
                    if cy > y + h and h > 0:
                        break
                    lw = medir(linea)
                    if alineacion == "centro":
                        cx = x + max(0, (w - lw) / 2)
                    elif alineacion == "derecha":
                        cx = x + max(0, w - lw)
                    else:
                        cx = x
                    draw.text((cx, cy), linea, font=fuente, fill=color)
                    cy += lh
            elif tipo == "imagen" and el.get("ruta") and os.path.exists(el["ruta"]):
                sub = Image.open(el["ruta"]).convert("RGBA")
                sub = sub.resize((max(1, w), max(1, h)))
                img.paste(sub, (x, y), sub)
            elif tipo == "qr" and el.get("payload"):
                import qrcode
                qr_img = qrcode.make(el["payload"]).convert("RGBA")
                qr_img = qr_img.resize((max(1, w), max(1, h)))
                img.paste(qr_img, (x, y), qr_img)
            elif tipo == "forma":
                forma = el.get("forma")
                color = _hex_a_rgb(el.get("color") or "#000000")
                relleno = bool(el.get("relleno"))
                grosor = max(1, mm_px(el.get("grosor_mm") or 1))
                if forma == "rectangulo":
                    draw.rectangle([x, y, x + w, y + h],
                                   fill=color if relleno else None,
                                   outline=color, width=grosor)
                elif forma == "circulo":
                    draw.ellipse([x, y, x + w, y + h],
                                fill=color if relleno else None,
                                outline=color, width=grosor)
                elif forma == "linea":
                    draw.line([x, y, x + w, y + h], fill=color, width=grosor)
        except Exception as e:
            logger.debug("render_png: omitido un elemento (%s): %s", el.get("tipo"), e)
            continue

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── PDF listo para imprenta (reportlab) — sangrado + marcas de corte/plegado ─────────────────
def render_pdf(doc: dict, ruta: str, *, sangrado_mm=3, marcas_corte=True) -> bool:
    """Genera el PDF en `ruta` a tamaño real (puntos reportlab), con sangrado (bleed) real
    ampliando el fondo/elementos hasta el borde de página y, opcionalmente, marcas de corte en
    las 4 esquinas y líneas de plegado (dípticos/trípticos). Devuelve True/False, nunca lanza."""
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception as e:
        logger.warning("render_pdf: reportlab no disponible: %s", e)
        return False

    ancho_mm = float(doc.get("ancho_mm") or 0)
    alto_mm = float(doc.get("alto_mm") or 0)
    if ancho_mm <= 0 or alto_mm <= 0:
        logger.warning("render_pdf: dimensiones inválidas (%s x %s mm)", ancho_mm, alto_mm)
        return False
    sangrado = max(0.0, float(sangrado_mm or 0))

    pagina_ancho = (ancho_mm + 2 * sangrado) * mm
    pagina_alto = (alto_mm + 2 * sangrado) * mm
    # Desplazamiento del origen de corte dentro de la página con sangrado (el contenido se
    # coloca igual que en el lienzo de edición, solo desplazado `sangrado` mm hacia dentro).
    off_x, off_y = sangrado * mm, sangrado * mm

    try:
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        c = rl_canvas.Canvas(ruta, pagesize=(pagina_ancho, pagina_alto))

        def X(v_mm):
            return off_x + float(v_mm or 0) * mm

        def Y(v_mm, h_mm=0):
            # reportlab mide Y desde ABAJO; el modelo de contenido mide Y desde ARRIBA.
            return pagina_alto - off_y - (float(v_mm or 0) + float(h_mm or 0)) * mm

        # Fondo: se extiende HASTA el borde de la página (incluido el sangrado), nunca deja un
        # marco blanco alrededor del cartel cuando se recorta por la línea de sangrado real.
        c.setFillColor(HexColor(doc.get("fondo_color") or "#FFFFFF"))
        c.rect(0, 0, pagina_ancho, pagina_alto, fill=1, stroke=0)

        for el in _elementos_ordenados(doc):
            try:
                _dibujar_elemento_pdf(c, el, X, Y)
            except Exception as e:
                logger.debug("render_pdf: omitido un elemento (%s): %s", el.get("tipo"), e)

        if marcas_corte and sangrado > 0:
            _marcas_de_corte(c, pagina_ancho, pagina_alto, off_x, off_y)
        _lineas_de_plegado(c, doc.get("modo"), ancho_mm, alto_mm, off_x, off_y, pagina_alto)

        c.showPage()
        c.save()
        return True
    except Exception as e:
        logger.warning("render_pdf: %s", e)
        return False


def _dibujar_elemento_pdf(c, el, X, Y):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm

    tipo = el.get("tipo")
    w_mm, h_mm = float(el.get("w") or 0), float(el.get("h") or 0)
    if tipo == "texto":
        negrita = "negrita" in (el.get("fuente") or "")
        regular, bold = _registrar_fuentes_reportlab()
        nombre_fuente = bold if negrita else regular
        tamano_pt = float(el.get("tamano_pt") or 14)
        c.setFont(nombre_fuente, tamano_pt)
        c.setFillColor(HexColor(el.get("color") or "#000000"))
        interlineado = float(el.get("interlineado") or 1.2)
        lh_mm = (tamano_pt * interlineado) / 72 * MM_POR_PULGADA
        alineacion = el.get("alineacion") or "izquierda"

        def medir(s):
            return c.stringWidth(s, nombre_fuente, tamano_pt)
        lineas = _envolver_texto(el.get("texto") or "", medir, max(w_mm * mm, 1))
        cy_mm = el.get("y") or 0
        for linea in lineas:
            if h_mm and (cy_mm - (el.get("y") or 0)) > h_mm:
                break
            lw = medir(linea)
            if alineacion == "centro":
                cx = X(el.get("x")) + max(0, (w_mm * mm - lw) / 2)
            elif alineacion == "derecha":
                cx = X(el.get("x")) + max(0, w_mm * mm - lw)
            else:
                cx = X(el.get("x"))
            # baseline ~= tamano_pt*0.8 por debajo del tope de línea (aproximación estándar);
            # ambos ya en puntos (unidad nativa de reportlab), sin conversión mm de por medio.
            c.drawString(cx, Y(cy_mm) - tamano_pt * 0.8, linea)
            cy_mm += lh_mm
    elif tipo == "imagen" and el.get("ruta") and os.path.exists(el["ruta"]):
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(el["ruta"]), X(el.get("x")), Y(el.get("y"), h_mm),
                   width=w_mm * mm, height=h_mm * mm, mask="auto")
    elif tipo == "qr" and el.get("payload"):
        import qrcode
        from reportlab.lib.utils import ImageReader
        buf = io.BytesIO()
        qrcode.make(el["payload"]).save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), X(el.get("x")), Y(el.get("y"), h_mm),
                   width=w_mm * mm, height=h_mm * mm, mask="auto")
    elif tipo == "forma":
        forma = el.get("forma")
        color = HexColor(el.get("color") or "#000000")
        relleno = bool(el.get("relleno"))
        grosor = max(0.1, float(el.get("grosor_mm") or 1))
        c.setFillColor(color)
        c.setStrokeColor(color)
        c.setLineWidth(grosor * mm)
        x0, y0 = X(el.get("x")), Y(el.get("y"), h_mm)
        if forma == "rectangulo":
            c.rect(x0, y0, w_mm * mm, h_mm * mm, fill=1 if relleno else 0, stroke=1)
        elif forma == "circulo":
            c.ellipse(x0, y0, x0 + w_mm * mm, y0 + h_mm * mm, fill=1 if relleno else 0, stroke=1)
        elif forma == "linea":
            c.line(X(el.get("x")), Y(el.get("y")), X(el.get("x")) + w_mm * mm,
                  Y(el.get("y")) - h_mm * mm)


_FUENTE_CACHE_RL = None


def _registrar_fuentes_reportlab():
    """Igual patrón que `utils/factura_pdf._registrar_fuente` (TTF Unicode con fallback a
    Helvetica) — duplicado deliberadamente aquí en vez de importar ese módulo de facturación,
    que es de otro dominio (facturas) y no una dependencia de la que depender para carteles."""
    global _FUENTE_CACHE_RL
    if _FUENTE_CACHE_RL is not None:
        return _FUENTE_CACHE_RL
    regular, bold = "Helvetica", "Helvetica-Bold"
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        reg_path = _candidatos_ttf(False)[0]
        bold_path = _candidatos_ttf(True)[0]
        if os.path.exists(reg_path):
            pdfmetrics.registerFont(TTFont("SMCartelUni", reg_path))
            regular = "SMCartelUni"
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("SMCartelUni-Bold", bold_path))
                bold = "SMCartelUni-Bold"
            else:
                bold = regular
    except Exception as e:
        logger.debug("registrar fuente PDF cartel: %s", e)
    _FUENTE_CACHE_RL = (regular, bold)
    return _FUENTE_CACHE_RL


def _marcas_de_corte(c, pagina_ancho, pagina_alto, off_x, off_y, largo_pt=18, hueco_pt=6):
    """Marcas de corte estándar de imprenta: 4 pares de líneas cortas en cada esquina, fuera de
    la línea de sangrado, apuntando hacia el borde de corte real."""
    c.setLineWidth(0.4)
    c.setStrokeColorRGB(0, 0, 0)
    esquinas_x = (off_x, pagina_ancho - off_x)
    esquinas_y = (off_y, pagina_alto - off_y)
    for ex in esquinas_x:
        signo_x = 1 if ex == esquinas_x[0] else -1
        for ey in esquinas_y:
            signo_y = 1 if ey == esquinas_y[0] else -1
            # Horizontal: desde el borde de página hacia la esquina de corte, con un hueco.
            c.line(ex + signo_x * (hueco_pt + largo_pt), ey, ex + signo_x * hueco_pt, ey)
            # Vertical.
            c.line(ex, ey + signo_y * (hueco_pt + largo_pt), ex, ey + signo_y * hueco_pt)


def _lineas_de_plegado(c, modo, ancho_mm, alto_mm, off_x, off_y, pagina_alto):
    """Líneas discontinuas de plegado para folletos díptico (1 línea central) y tríptico
    (2 líneas a 1/3 y 2/3 del ancho) — solo horizontalmente (plegado vertical del folleto A4
    apaisado), que es el plegado estándar de folletos de mano."""
    from reportlab.lib.units import mm
    if modo not in ("diptico", "triptico"):
        return
    c.saveState()
    c.setDash(4, 3)
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    cortes = [ancho_mm / 2] if modo == "diptico" else [ancho_mm / 3, 2 * ancho_mm / 3]
    for x_mm in cortes:
        x = off_x + x_mm * mm
        c.line(x, off_y, x, off_y + alto_mm * mm)
    c.restoreState()
