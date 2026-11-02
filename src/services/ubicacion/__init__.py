"""Ubicación de artículos en tienda/almacén — capa fina para consumidores que no deben hablar con la
BD directamente (p. ej. la REST API). Mismo modelo de datos que usa el escritorio
(`gui/ubicacion_tienda.py`): ambos ámbitos, LINEAL (tienda) y ALMACÉN, viven en la misma fila de
`ubicaciones` por `codigo_articulo`, en columnas distintas (`db.ubicaciones.py::asignar_ubicacion`)."""


def buscar(id_empresa, texto: str = "", limite: int = 50) -> list[dict]:
    """Busca artículos por código o nombre y devuelve su ubicación física — LINEAL y ALMACÉN, más
    stock — igual de rica que la pestaña "Buscar producto" de escritorio. Artículos sin ninguna fila
    en `ubicaciones` (LEFT JOIN) salen con esos campos a `None` — se muestran como "sin ubicación
    asignada", nunca se ocultan ni se finge una ubicación que no existe."""
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    like = f"%{texto}%"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT a.codigo, a.nombre, a.ubicacion_tienda, a.ubicacion_almacen, "
                "u.pasillo, u.estanteria, u.balda, u.verificado, "
                "u.pasillo_almacen, u.estanteria_almacen, u.nivel_almacen, "
                "COALESCE(a.Stock_tienda, 0) AS stock_tienda, COALESCE(a.Stock_total, 0) AS stock_total "
                "FROM articulos a LEFT JOIN ubicaciones u ON u.codigo_articulo = a.codigo "
                "WHERE a.id_empresa=%s AND (a.codigo LIKE %s OR a.nombre LIKE %s) "
                "ORDER BY a.nombre ASC LIMIT %s",
                (id_empresa, like, like, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []


def asignar(id_empresa, codigo, pasillo, estanteria, nivel, tipo: str) -> dict:
    """Asigna la ubicación LINEAL o ALMACÉN de un artículo. `tipo`: "lineal"|"almacen"."""
    codigo = (codigo or "").strip()
    pasillo = (pasillo or "").strip()
    estanteria = (estanteria or "").strip()
    nivel = (nivel or "").strip()
    if not (codigo and pasillo and estanteria and nivel):
        return {"ok": False, "error": "Código, pasillo, estantería y nivel son obligatorios."}
    if tipo not in ("lineal", "almacen"):
        return {"ok": False, "error": "Tipo inválido (usa 'lineal' o 'almacen')."}
    from src.db import ubicaciones as _db
    return _db.asignar_ubicacion(codigo, pasillo, estanteria, nivel, tipo == "lineal",
                                 id_empresa=id_empresa)


def mapa_info(planta_index=None) -> dict | None:
    """Calibración + infraestructura de la planta (sin la ruta de fichero cruda del servidor —
    se sirve aparte por `/location/map/image`). `planta_index=None` -> primera planta con imagen."""
    from src.db import ubicaciones as _db
    if planta_index is None:
        planta_index = _db.primera_planta_con_imagen()
    if planta_index is None:
        return None
    info = _db.plano_info_completo(planta_index)
    if not info:
        return None
    tipo, titulo, ruta_imagen = info
    cfg = _db.config_plano(planta_index)
    escala = ancla_x = ancla_y = None
    puntos = []
    if cfg:
        _ruta, escala, ancla_x, ancla_y, _muros, _puntos = cfg
    try:
        puntos = _db.puntos_infraestructura(planta_index)
    except Exception:
        puntos = []
    return {
        "planta_index": planta_index, "tipo": tipo, "titulo": titulo,
        "escala_px_metro": float(escala) if escala else None,
        "ancla_x": float(ancla_x) if ancla_x is not None else None,
        "ancla_y": float(ancla_y) if ancla_y is not None else None,
        "puntos_infraestructura": puntos or [],
        "tiene_imagen": bool(ruta_imagen),
    }


def imagen_absoluta(planta_index) -> str | None:
    """Ruta absoluta de la imagen del plano, ACOTADA a `documentos/planos/` (solo se usa el nombre de
    fichero, nunca la ruta cruda guardada en BD) — evita cualquier recorrido de directorios."""
    import os
    from src.db import ubicaciones as _db
    ruta = _db.ruta_imagen(planta_index)
    if not ruta:
        return None
    nombre = os.path.basename(ruta)
    base = os.path.abspath(os.path.join(os.getcwd(), "documentos", "planos"))
    candidato = os.path.abspath(os.path.join(base, nombre))
    if os.path.commonpath([base, candidato]) != base:
        return None
    return candidato if os.path.isfile(candidato) else None


def coords_articulo(codigo) -> dict | None:
    from src.db import ubicaciones as _db
    coord = _db.coords_por_articulo((codigo or "").strip())
    if not coord or coord[0] is None:
        return None
    return {"x": float(coord[0]), "y": float(coord[1])}


def _resolver_punto(planta_index, ref: dict) -> dict | None:
    """`ref` = {"tipo":"articulo","codigo":...} | {"tipo":"punto","x":...,"y":...}."""
    if not isinstance(ref, dict):
        return None
    if ref.get("tipo") == "punto":
        try:
            return {"x": float(ref["x"]), "y": float(ref["y"])}
        except (KeyError, TypeError, ValueError):
            return None
    if ref.get("tipo") == "articulo":
        return coords_articulo(ref.get("codigo"))
    return None


def calcular_ruta(planta_index, origen: dict, destino: dict) -> dict:
    """Calcula la ruta (A*) entre `origen` y `destino` sobre el plano de `planta_index`. Honesto: nunca
    inventa una ruta — si falta el plano o no se puede localizar un extremo, devuelve el motivo."""
    from src.db import ubicaciones as _db
    from src.services.ubicacion import pathfinding

    if planta_index is None:
        planta_index = _db.primera_planta_con_imagen()
    if planta_index is None:
        return {"ok": False, "motivo": "sin_plano"}

    cfg = _db.config_plano(planta_index)
    if not cfg:
        return {"ok": False, "motivo": "sin_plano"}
    ruta_img, _escala, _ax, _ay, muros_json, _puntos = cfg
    ruta_abs = imagen_absoluta(planta_index)
    if not ruta_abs:
        return {"ok": False, "motivo": "sin_plano"}

    p_origen = _resolver_punto(planta_index, origen)
    if not p_origen:
        return {"ok": False, "motivo": "origen_no_localizado"}
    p_destino = _resolver_punto(planta_index, destino)
    if not p_destino:
        return {"ok": False, "motivo": "destino_no_localizado"}

    import json
    try:
        _muros_data = json.loads(muros_json) if muros_json else {}
        # `muros_vectoriales` es un objeto {"muros_vectores": [...], "calibracion": {...}, "ancla": {...}}
        # — los segmentos de muro viven bajo la clave "muros_vectores", no en la raíz.
        muros = _muros_data.get("muros_vectores", []) if isinstance(_muros_data, dict) else (_muros_data or [])
    except Exception:
        muros = []

    try:
        from PIL import Image
        with Image.open(ruta_abs) as im:
            ancho_px, alto_px = im.size
    except Exception:
        return {"ok": False, "motivo": "sin_plano"}

    celda = 20
    matriz = pathfinding.construir_matriz(muros, ancho_px, alto_px, celda_size=celda)
    finder = pathfinding.PathFinder(matriz)
    inicio = (int(p_origen["y"] // celda), int(p_origen["x"] // celda))
    fin = (int(p_destino["y"] // celda), int(p_destino["x"] // celda))
    celdas = finder.get_path(inicio, fin)
    if not celdas:
        return {"ok": False, "motivo": "sin_ruta"}

    puntos_px = [{"x": c[1] * celda + celda / 2, "y": c[0] * celda + celda / 2} for c in celdas]
    return {"ok": True, "ruta": puntos_px, "distancia_celdas": len(celdas)}
