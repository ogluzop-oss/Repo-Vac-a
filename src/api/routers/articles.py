"""
Router /articles — consulta básica de artículos (nombre/descripción/precio/categoría), solo lectura.
Consume `src.services.articulos`.

Distinto de `/catalogo/productos` (`routers/catalog.py`): ese es el catálogo PIM/e-commerce, filtrado
por visibilidad web y con el código interno oculto salvo para ADMINISTRADOR/SUPERADMIN — no sirve para
que un OPERARIO de tienda consulte cualquier artículo. Ver `services/articulos/__init__.py`.

Sin permiso RBAC dedicado todavía (no existe `articulos.ver` en el catálogo de
`seguridad/catalogo.py`): exige solo autenticación, igual que `/location` y `/orders`.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/articles")
    @requiere_auth()
    def articles_buscar():
        from flask import g, jsonify, request
        from src.services import articulos
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 50))
        res = articulos.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))

    @bp.get("/articles/<codigo>/image")
    @requiere_auth()
    def articles_imagen(codigo):
        import os

        from flask import g, send_file
        from src.db.articulos import obtener_imagen
        ruta = obtener_imagen(codigo, id_empresa=g.ctx["id_empresa"])
        if not ruta or not os.path.isfile(ruta):
            return {"error": "El artículo no tiene foto disponible."}, 404
        return send_file(ruta)

    @bp.post("/articles/<codigo>/image")
    @requiere_auth()
    def articles_imagen_subir(codigo):
        """Sube/reemplaza la foto del artículo desde el móvil (cámara o galería) — EXACTO mismo
        destino/convención de nombre que `gui.info_articulo._ImagenArticuloPage._guardar_imagen`
        en escritorio (`documentos/imagenes_articulos/<código><ext>`), así ambos ven/editan la
        MISMA imagen, nunca una copia paralela."""
        import os

        from flask import g, jsonify, request
        from src.db.articulos import actualizar_imagen, obtener_articulo
        id_empresa = g.ctx["id_empresa"]
        if not obtener_articulo(codigo, id_empresa=id_empresa):
            return jsonify({"error": "Este código de artículo no existe en el sistema."}), 404
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"error": "Falta el fichero de imagen ('foto')."}), 400
        try:
            raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            destino_dir = os.path.join(raiz, "documentos", "imagenes_articulos")
            os.makedirs(destino_dir, exist_ok=True)
            ext = os.path.splitext(foto.filename)[1].lower() or ".jpg"
            safe = "".join(c for c in str(codigo) if c.isalnum() or c in ("-", "_")) or "articulo"
            destino = os.path.join(destino_dir, f"{safe}{ext}")
            foto.save(destino)
            actualizar_imagen(codigo, destino, id_empresa=id_empresa)
        except Exception as e:
            return jsonify({"error": f"No se pudo guardar la imagen: {e}"}), 500
        return jsonify({"ok": True})

    @bp.delete("/articles/<codigo>/image")
    @requiere_auth()
    def articles_imagen_borrar(codigo):
        import os

        from flask import g, jsonify
        from src.db.articulos import actualizar_imagen, obtener_imagen
        id_empresa = g.ctx["id_empresa"]
        ruta_actual = obtener_imagen(codigo, id_empresa=id_empresa)
        actualizar_imagen(codigo, None, id_empresa=id_empresa)
        if ruta_actual and os.path.exists(ruta_actual):
            try:
                os.remove(ruta_actual)
            except OSError:
                pass
        return jsonify({"ok": True})

    @bp.get("/articles/<codigo>/ficha")
    @requiere_auth()
    def articles_ficha(codigo):
        """Ficha completa de un artículo — EXACTAMENTE los mismos datos que
        `gui.info_articulo.InfoArticuloWindow._buscar` muestra en escritorio (petición explícita:
        "los mismos datos, sin excepción"), reutilizando las mismas funciones de servicio/datos
        que ya usa esa pantalla (nunca una segunda consulta/lógica paralela)."""
        from flask import g, jsonify

        from src.db.conexion import obtener_articulo, ventas_semana
        id_empresa = g.ctx["id_empresa"]

        art = obtener_articulo(codigo, id_empresa=id_empresa)
        if not art:
            # Búsqueda unificada (mismo criterio que escritorio): si no es un código interno,
            # puede ser la referencia original de un proveedor.
            try:
                from src.db import equivalencias_proveedor as _EQ
                codigo_resuelto = _EQ.resolver_por_referencia(codigo, id_empresa=id_empresa)
            except Exception:
                codigo_resuelto = None
            if codigo_resuelto:
                art = obtener_articulo(codigo_resuelto, id_empresa=id_empresa)
        if not art:
            return jsonify({"error": "Este código de artículo no existe en el sistema."}), 404

        codigo_real = art.get("codigo")

        reservado = 0
        try:
            from src.services.comercio_digital.inventario import reservas as _RSV
            reservado = int(_RSV.reservado(codigo_real, id_empresa=id_empresa) or 0)
        except Exception:
            pass

        precio = float(art.get("precio_promo") if art.get("promo_activa")
                       else (art.get("precio") or 0))

        precio_ref = None
        try:
            from src.services.compras import precios_dinamicos as PD
            precio_ref = PD.precio_referencia(codigo_real, id_empresa=id_empresa)
        except Exception:
            pass

        familia = None
        try:
            from src.db.familias import familia_de_articulo
            fam = familia_de_articulo(codigo_real, id_empresa=id_empresa)
            familia = fam.get("nombre") if fam else None
        except Exception:
            pass

        ventas7 = 0
        try:
            ventas7 = int(ventas_semana(codigo_real) or 0)
        except Exception:
            pass

        def _num(v):
            # Columnas DECIMAL de MariaDB llegan como `Decimal`, no serializable por `jsonify`
            # directamente (mismo cuidado que ya tiene `mobile_client/src/api/articles.ts` con
            # `precio`/`precio_promo`).
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return jsonify({
            "codigo": codigo_real,
            "nombre": art.get("nombre"),
            "stock_lineal": _num(art.get("Stock_tienda")),
            "stock_almacen": _num(art.get("Stock_total")),
            "stock_central": _num(art.get("Stock_central")),
            "stock_reservado": reservado,
            "precio": precio,
            "ubicacion_tienda": art.get("ubicacion_tienda"),
            "ubicacion_almacen": art.get("ubicacion_almacen"),
            "proxima_recepcion": (str(art.get("siguiente_recepcion"))
                                  if art.get("siguiente_recepcion") else None),
            "ventas_7_dias": ventas7,
            "familia": familia,
            "precio_ref": _num(precio_ref),
            "peso_unitario": _num(art.get("peso_unitario")),
            "tolerancia_peso": _num(art.get("tolerancia_peso")),
            "requiere_lote": bool(art.get("requiere_lote")),
            "tiene_imagen": bool(art.get("imagen")),
        })
