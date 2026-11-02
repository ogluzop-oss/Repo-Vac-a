"""
Generación de etiquetas de precio en PDF (papel). `GeneradorEtiquetas` es lógica pura (reportlab +
`divisas`, sin Qt) — vivía dentro de `gui/etiquetas_precios.py`, que además importa PyQt6 a nivel de
módulo; se extrae aquí (Strangler Pattern) para poder llamarla desde un proceso headless (REST API)
sin arrastrar Qt. `gui/etiquetas_precios.py` importa la clase desde este módulo, sin cambios de
comportamiento para sus llamadores existentes.
"""

import os
from datetime import datetime

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from src.utils import divisas


class GeneradorEtiquetas:
    TAMANOS = {
        "40x26": (40, 26),
        "65x35": (65, 35),
        "70x35": (70, 35),
        "95x35": (95, 35),
        "100x70": (100, 70),
        "148x70": (148, 70),
    }

    # Tipos de etiqueta: color del marco/banda y rótulo. "normal" = blanco (aspecto actual).
    TIPOS = {
        "normal":   {"color": "#111111", "banda": None,       "rotulo": None},
        "rebajado": {"color": "#F5871F", "banda": "#F5871F",  "rotulo": "REBAJADO"},
        "nuevo":    {"color": "#2FBF71", "banda": "#2FBF71",  "rotulo": "NUEVO"},
    }

    @staticmethod
    def generar(codigo, nombre, precio, formato="70x35", tipo="normal", seccion=None):
        w_mm, h_mm = GeneradorEtiquetas.TAMANOS.get(formato, (70, 35))
        cfg_tipo = GeneradorEtiquetas.TIPOS.get(tipo, GeneradorEtiquetas.TIPOS["normal"])

        folder = os.path.join(os.getcwd(), "documentos", "etiquetas")
        os.makedirs(folder, exist_ok=True)

        filename = f"ETQ_{codigo}_{datetime.now().strftime('%H%M%S')}.pdf"
        path = os.path.join(folder, filename)

        W, H = w_mm * mm, h_mm * mm
        c = canvas.Canvas(path, pagesize=(W, H))

        grande = h_mm >= 55          # 100x70 · 148x70
        peque = h_mm < 30            # 40x26
        pad = 3.2 * mm

        # Fondo blanco + marco redondeado (color según el tipo de etiqueta).
        c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
        inset = 1.3 * mm
        _es_normal = cfg_tipo.get("rotulo") is None
        c.setStrokeColor(colors.HexColor(cfg_tipo["color"]))
        c.setLineWidth(1.1 if _es_normal else 2.2)
        c.roundRect(inset, inset, W - 2 * inset, H - 2 * inset,
                    min(3 * mm, H * 0.09), stroke=1, fill=0)

        # Rótulo de tipo (REBAJADO / NUEVO): pastilla de color en la esquina superior derecha.
        if cfg_tipo.get("banda") and cfg_tipo.get("rotulo"):
            fs_tag = 8 if h_mm >= 55 else (5 if h_mm < 30 else 6.5)
            tag = cfg_tipo["rotulo"]
            tag_pad = 1.6 * mm
            tag_w = c.stringWidth(tag, "Helvetica-Bold", fs_tag) + 2 * tag_pad
            tag_h = fs_tag * 0.9 + 1.4 * mm
            tag_x = W - inset - 1.1 * mm - tag_w
            tag_y = H - inset - 1.1 * mm - tag_h
            c.setFillColor(colors.HexColor(cfg_tipo["banda"]))
            c.roundRect(tag_x, tag_y, tag_w, tag_h, tag_h * 0.35, stroke=0, fill=1)
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", fs_tag)
            c.drawString(tag_x + tag_pad, tag_y + (tag_h - fs_tag * 0.72) / 2, tag)

        # ── Nombre del producto (arriba, izq.) — truncado al ancho disponible ──
        fs_nom = 16 if grande else (8 if peque else 11)
        nom = (nombre or "").upper()
        max_w = W - 2 * pad
        while nom and c.stringWidth(nom, "Helvetica-Bold", fs_nom) > max_w:
            nom = nom[:-1]
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", fs_nom)
        nom_baseline = H - inset - pad * 0.6 - fs_nom * 0.8
        c.drawString(pad, nom_baseline, nom)

        # ── Separador fino ──
        sep_y = nom_baseline - fs_nom * 0.45
        c.setLineWidth(0.7); c.setStrokeColor(colors.HexColor("#CCCCCC"))
        c.line(pad, sep_y, W - pad, sep_y)

        # ── Código de barras (abajo, izq.) + REF debajo ──
        bc_h = (13 if grande else (4.5 if peque else 6.5)) * mm
        bar_w = 0.5 if grande else (0.3 if peque else 0.38)
        fs_ref = 9 if grande else (5.5 if peque else 6.5)
        ref_baseline = inset + 1.6 * mm
        bc_y = ref_baseline + fs_ref * 0.5 + 1.0 * mm
        try:
            bc = code128.Code128(str(codigo), barHeight=bc_h, barWidth=bar_w)
            bc.drawOn(c, pad, bc_y)
        except Exception:
            pass
        texto_ref = f"REF: {codigo}" + (f"   ·   {seccion}" if seccion else "")
        c.setFillColor(colors.HexColor("#333333")); c.setFont("Helvetica", fs_ref)
        c.drawString(pad, ref_baseline, texto_ref)

        # ── Precio destacado (derecha, banda media) ──
        precio_str = divisas.formatear(float(precio))
        fs_precio = 42 if grande else (18 if peque else 28)
        ancho_max = W - 2 * pad - 2.5 * mm          # margen extra para que el símbolo no roce el marco
        while fs_precio > 8 and c.stringWidth(precio_str, "Helvetica-Bold", fs_precio) > ancho_max:
            fs_precio -= 1
        zona_top, zona_bot = sep_y, bc_y + bc_h
        precio_baseline = (zona_top + zona_bot) / 2 - fs_precio * 0.34
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", fs_precio)
        c.drawRightString(W - pad - 1.5 * mm, precio_baseline, precio_str)

        c.save()
        return path


def cambiar_precio_y_generar(codigo, nuevo_precio, id_empresa=None, id_tienda=None, id_usuario=None,
                              formato="70x35", tipo="normal") -> dict:
    """Cambia el precio del artículo Y genera su etiqueta de papel con el precio nuevo — mismo flujo que
    `gui/etiquetas_precios.py` (cambiar precio + imprimir), expuesto aquí para la REST API (móvil).
    Distinto de `generar_para_articulo` (reimpresión sin tocar el precio)."""
    codigo = (codigo or "").strip()
    if not codigo:
        return {"ok": False, "error": "Código obligatorio."}
    try:
        nuevo_precio = float(nuevo_precio)
        if nuevo_precio < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "error": "Precio inválido."}

    from src.db.conexion import obtener_articulo
    art = obtener_articulo(codigo, id_empresa=id_empresa)
    if not art:
        return {"ok": False, "error": "Artículo no encontrado."}

    from src.db.articulos import actualizar_precio
    actualizar_precio(codigo, nuevo_precio, id_empresa=id_empresa)

    if formato not in GeneradorEtiquetas.TAMANOS:
        formato = "70x35"
    if tipo not in GeneradorEtiquetas.TIPOS:
        tipo = "normal"
    ruta = GeneradorEtiquetas.generar(codigo, art.get("nombre") or codigo, nuevo_precio, formato, tipo,
                                      seccion=art.get("seccion"))

    id_documento = None
    try:
        from src.db.documentos import registrar_documento
        id_documento = registrar_documento(ruta, tipo="etiqueta", nombre=os.path.basename(ruta),
                                           referencia=str(codigo), id_empresa=id_empresa,
                                           id_tienda=id_tienda, id_usuario=id_usuario)
    except Exception:
        pass

    try:
        from src.services import eventos as _EV
        _EV.publicar("PRECIO_ACTUALIZADO", origen="etiquetas", ref_entidad="articulo", ref_id=codigo,
                     payload={"codigo": codigo, "nombre": art.get("nombre"), "precio": nuevo_precio})
    except Exception:
        pass

    return {"ok": True, "id_documento": id_documento, "archivo": os.path.basename(ruta)}


def generar_para_articulo(codigo, id_empresa=None, id_tienda=None, id_usuario=None,
                           formato="70x35", tipo="normal") -> dict:
    """Genera la etiqueta PDF de un artículo EXISTENTE con su precio vigente (reimpresión — no cambia
    el precio, a diferencia del flujo de escritorio que genera la etiqueta tras editar el precio).
    Registra el PDF en el registro documental (mismo criterio que el escritorio)."""
    codigo = (codigo or "").strip()
    if not codigo:
        return {"ok": False, "error": "Código obligatorio."}

    from src.db.conexion import obtener_articulo
    art = obtener_articulo(codigo, id_empresa=id_empresa)
    if not art:
        return {"ok": False, "error": "Artículo no encontrado."}

    from src.services.esl.sync import precio_efectivo
    precio = precio_efectivo(codigo, id_empresa)
    if precio is None:
        return {"ok": False, "error": "El artículo no tiene precio."}

    if formato not in GeneradorEtiquetas.TAMANOS:
        formato = "70x35"
    if tipo not in GeneradorEtiquetas.TIPOS:
        tipo = "normal"

    ruta = GeneradorEtiquetas.generar(codigo, art.get("nombre") or codigo, precio, formato, tipo,
                                      seccion=art.get("seccion"))

    try:
        from src.db.documentos import registrar_documento
        registrar_documento(ruta, tipo="etiqueta", nombre=os.path.basename(ruta),
                            referencia=str(codigo), id_empresa=id_empresa, id_tienda=id_tienda,
                            id_usuario=id_usuario)
    except Exception:
        pass

    return {"ok": True, "archivo": os.path.basename(ruta)}
