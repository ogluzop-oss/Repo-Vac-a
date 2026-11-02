"""
Catálogo B2B del proveedor (Smart Suppliers · Fase A). Alta manual e import masivo (CSV/Excel) de
artículos ofertados, con Unidad de Medida Mayorista y Cantidad Mínima de Pedido (MOQ) OBLIGATORIAS
(requisito explícito: sin unidad no hay alta posible). El import masivo NO parsea el fichero aquí (eso
es responsabilidad de la vista/edge, ver `src/backend/portal_proveedor.py`) — recibe una lista de filas
ya parseadas y valida/audita cada una, para poder mostrarle al proveedor exactamente qué falló.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_catalogo")

UNIDADES_MAYORISTA = ("kg", "unidad", "pale", "caja")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def _validar(codigo, nombre, unidad_medida, moq, precio_unitario, *, es_perecedero=False,
            lote=None, fecha_caducidad=None, disponible_consignacion=False,
            comision_unitaria=None, talla=None, marca=None, color=None,
            exigir_atributos=False) -> str | None:
    """Devuelve el motivo del error, o None si la fila es válida.

    Trazabilidad (Punto 3 bis): si el artículo se marca "Perecedero", el proveedor DEBE declarar
    ya en el catálogo el lote y la fecha de caducidad/consumo preferente — es la fuente de verdad
    que viajará con el pedido y con la que la Empresa recibirá la mercancía (nunca los inventa el
    operario de almacén después).

    Consignación (Portal B2B, Fase 1): mismo patrón condicional — `comision_unitaria` solo se exige
    (y debe ser >= 0) cuando el proveedor marca el artículo como `disponible_consignacion`; si no,
    no aplica y no se valida.

    Talla/Marca/Color (petición explícita, detección preventiva de duplicados — los 3 parámetros
    estructurados que, junto al Nombre, usa `db.articulos.detectar_posible_duplicado`): la
    exigencia vive AQUÍ, en la función de servicio compartida, pero es OPT-IN vía
    `exigir_atributos` (por defecto `False`) — esta función la comparten otros llamantes legítimos
    (tests, altas internas) para los que esos campos no aplican y que no deben romperse. El borde
    real del portal de proveedores (`backend.portal_proveedor::catalogo_nuevo`/`catalogo_importar`,
    vía `crear_articulo(..., exigir_atributos=True)`) es quien activa la exigencia."""
    if not str(codigo or "").strip():
        return "codigo_obligatorio"
    if not str(nombre or "").strip():
        return "nombre_obligatorio"
    if unidad_medida not in UNIDADES_MAYORISTA:
        return f"unidad_medida_invalida (válidas: {', '.join(UNIDADES_MAYORISTA)})"
    try:
        if int(moq) < 1:
            return "moq_debe_ser_mayor_o_igual_a_1"
    except (TypeError, ValueError):
        return "moq_invalido"
    try:
        if float(precio_unitario) < 0:
            return "precio_no_puede_ser_negativo"
    except (TypeError, ValueError):
        return "precio_invalido"
    if es_perecedero:
        if not str(lote or "").strip():
            return "lote_obligatorio_para_perecedero"
        if not str(fecha_caducidad or "").strip():
            return "fecha_caducidad_obligatoria_para_perecedero"
    if disponible_consignacion:
        try:
            if float(comision_unitaria) < 0:
                return "comision_unitaria_no_puede_ser_negativa"
        except (TypeError, ValueError):
            return "comision_unitaria_obligatoria_para_consignacion"
    if exigir_atributos:
        if not str(talla or "").strip():
            return "talla_obligatoria"
        if not str(marca or "").strip():
            return "marca_obligatoria"
        if not str(color or "").strip():
            return "color_obligatorio"
    return None


def crear_articulo(id_suministrador, codigo: str, nombre: str, *, unidad_medida: str, moq: int = 1,
                   precio_unitario: float = 0, descripcion: str | None = None,
                   sector_id: int | None = None, es_perecedero=False, lote: str | None = None,
                   fecha_caducidad: str | None = None, disponible_consignacion=False,
                   comision_unitaria: float | None = None, talla: str | None = None,
                   marca: str | None = None, color: str | None = None,
                   exigir_atributos: bool = False) -> dict:
    es_perecedero = bool(es_perecedero) and str(es_perecedero) not in ("0", "False", "")
    lote = (lote or "").strip() or None
    fecha_caducidad = (fecha_caducidad or "").strip() or None
    if not es_perecedero:
        # No perecedero: lote/caducidad no aplican — nunca se guardan datos huérfanos aunque
        # el formulario los hubiera enviado (p. ej. al cambiar de opción sin limpiar los campos).
        lote = None
        fecha_caducidad = None
    disponible_consignacion = (bool(disponible_consignacion)
                               and str(disponible_consignacion) not in ("0", "False", ""))
    if not disponible_consignacion:
        # No disponible para consignación: la comisión no aplica — mismo criterio que
        # lote/fecha_caducidad arriba, nunca se guarda un dato huérfano.
        comision_unitaria = None
    error = _validar(codigo, nombre, unidad_medida, moq, precio_unitario,
                     es_perecedero=es_perecedero, lote=lote, fecha_caducidad=fecha_caducidad,
                     disponible_consignacion=disponible_consignacion,
                     comision_unitaria=comision_unitaria, talla=talla, marca=marca, color=color,
                     exigir_atributos=exigir_atributos)
    if error:
        return {"ok": False, "error": error}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_catalogo (id_suministrador, codigo, nombre, descripcion, "
                "unidad_medida, moq, precio_unitario, sector_id, es_perecedero, lote, "
                "fecha_caducidad, disponible_consignacion, comision_unitaria, talla, marca, color) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), descripcion=VALUES(descripcion), "
                "unidad_medida=VALUES(unidad_medida), moq=VALUES(moq), "
                "precio_unitario=VALUES(precio_unitario), activo=1, "
                "es_perecedero=VALUES(es_perecedero), lote=VALUES(lote), "
                "fecha_caducidad=VALUES(fecha_caducidad), "
                "disponible_consignacion=VALUES(disponible_consignacion), "
                "comision_unitaria=VALUES(comision_unitaria), talla=VALUES(talla), "
                "marca=VALUES(marca), color=VALUES(color)",
                (id_suministrador, codigo.strip(), nombre.strip(), descripcion, unidad_medida,
                 int(moq), float(precio_unitario), sector_id, int(es_perecedero), lote,
                 fecha_caducidad, int(disponible_consignacion),
                 float(comision_unitaria) if comision_unitaria is not None else None,
                 (talla or "").strip() or None, (marca or "").strip() or None,
                 (color or "").strip() or None))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("crear_articulo(%s,%s): %s", id_suministrador, codigo, e)
        return {"ok": False, "error": "error_interno"}


def desactivar_articulo(id_suministrador, codigo: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_catalogo SET activo=0 WHERE id_suministrador=%s AND codigo=%s",
                        (id_suministrador, codigo))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("desactivar_articulo: %s", e)
        return False


def listar_por_suministrador(id_suministrador, *, solo_activos=True) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM b2b_catalogo WHERE id_suministrador=%s"
            p = [id_suministrador]
            if solo_activos:
                q += " AND activo=1"
            q += " ORDER BY nombre"
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_por_suministrador(%s): %s", id_suministrador, e)
        return []


def buscar_para_empresa(sector_ids: set, *, texto: str | None = None, limite: int = 200) -> list[dict]:
    """Catálogo visible para una empresa compradora: SOLO artículos activos de proveedores cuyo
    `sector_id` esté en `sector_ids` (el propio + los marcados compatibles, ver `sectores.compatibles_de`).
    Aislamiento estricto: sin sectores compatibles, no hay resultados (nunca se muestra "todo" por
    defecto)."""
    if not sector_ids:
        return []
    try:
        ensure_schema()
        placeholders = ",".join(["%s"] * len(sector_ids))
        q = (f"SELECT c.*, s.razon_social AS proveedor_nombre FROM b2b_catalogo c "
             f"JOIN suministradores s ON s.id = c.id_suministrador "
             f"WHERE c.activo=1 AND c.sector_id IN ({placeholders})")
        params = list(sector_ids)
        if texto:
            q += " AND (c.nombre LIKE %s OR c.codigo LIKE %s)"
            params += [f"%{texto}%", f"%{texto}%"]
        q += " ORDER BY c.actualizado_en DESC LIMIT %s"
        params.append(int(limite))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, params)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("buscar_para_empresa: %s", e)
        return []


def articulos_disponibles_consignacion(id_suministrador, codigos: list) -> set:
    """Subconjunto de `codigos` que el proveedor tiene marcados `disponible_consignacion=1` en su
    catálogo activo. Usado tanto para decidir si mostrar la casilla "tramitar en consignación" en el
    checkout del Portal Empresa (`portal_empresa_b2b.py::pagina_carrito`), como para VALIDAR en el
    backend (`b2b_pedidos.tramitar`) que un pedido marcado como consignación corresponde de verdad a
    artículos flageados por el proveedor — nunca se confía solo en la casilla del cliente."""
    codigos = [c for c in (codigos or []) if c]
    if not id_suministrador or not codigos:
        return set()
    try:
        ensure_schema()
        placeholders = ",".join(["%s"] * len(codigos))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT codigo FROM b2b_catalogo WHERE id_suministrador=%s AND activo=1 "
                f"AND disponible_consignacion=1 AND codigo IN ({placeholders})",
                [id_suministrador, *codigos])
            return {_fila(cur, r)["codigo"] for r in cur.fetchall()}
    except Exception as e:
        logger.error("articulos_disponibles_consignacion(%s): %s", id_suministrador, e)
        return set()


def obtener_activo(id_suministrador, codigo: str) -> dict | None:
    """Un artículo concreto y activo del proveedor, o None (no existe / desactivado). Usado al
    re-resolver líneas de una plantilla (b2b_plantillas) contra el catálogo VIVO."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_catalogo WHERE id_suministrador=%s AND codigo=%s "
                        "AND activo=1", (id_suministrador, codigo))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener_activo(%s,%s): %s", id_suministrador, codigo, e)
        return None


# ── Precios escalonados por volumen (rappels) ────────────────────────────────
def guardar_escalones(id_suministrador, id_articulo, escalones: list[dict]) -> dict:
    """Reemplaza TODOS los escalones del artículo por los indicados. `escalones` =
    [{cantidad_desde, precio_unitario}, ...]. Verifica que el artículo pertenece al proveedor;
    valida cantidad_desde >= 1 y sin duplicados antes de tocar nada."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM b2b_catalogo WHERE id=%s AND id_suministrador=%s",
                        (id_articulo, id_suministrador))
            if not cur.fetchone():
                return {"ok": False, "error": "articulo_no_encontrado"}
            limpios = []
            vistos = set()
            for e in escalones:
                try:
                    cdesde = int(e.get("cantidad_desde"))
                    precio = float(e.get("precio_unitario"))
                except (TypeError, ValueError):
                    return {"ok": False, "error": "escalon_invalido"}
                if cdesde < 1 or precio < 0:
                    return {"ok": False, "error": "escalon_invalido"}
                if cdesde in vistos:
                    return {"ok": False, "error": "cantidad_desde_duplicada"}
                vistos.add(cdesde)
                limpios.append((cdesde, precio))
            cur.execute("DELETE FROM b2b_catalogo_escalones WHERE id_articulo=%s", (id_articulo,))
            for cdesde, precio in limpios:
                cur.execute(
                    "INSERT INTO b2b_catalogo_escalones (id_articulo, cantidad_desde, "
                    "precio_unitario) VALUES (%s,%s,%s)", (id_articulo, cdesde, precio))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("guardar_escalones(%s,%s): %s", id_suministrador, id_articulo, e)
        return {"ok": False, "error": "error_interno"}


def escalones_de(id_articulo) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_catalogo_escalones WHERE id_articulo=%s "
                        "ORDER BY cantidad_desde", (id_articulo,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("escalones_de(%s): %s", id_articulo, e)
        return []


def precio_para_cantidad(articulo: dict, cantidad) -> float:
    """Precio unitario aplicable: el `precio_unitario` base del artículo (piso, válido desde el MOQ)
    salvo que exista un escalón con cantidad_desde <= cantidad, en cuyo caso se usa el de mayor
    cantidad_desde aplicable. Degradable: si no hay escalones o falla la consulta, devuelve el precio
    base — nunca rompe el flujo de compra."""
    precio = float(articulo["precio_unitario"])
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        return precio
    try:
        for esc in escalones_de(articulo["id"]):
            if int(esc["cantidad_desde"]) <= cantidad:
                precio = float(esc["precio_unitario"])
    except Exception as e:
        logger.debug("precio_para_cantidad(%s): %s", articulo.get("id"), e)
    return precio


# ── Métricas de visibilidad (vistas/clics) ───────────────────────────────────
def registrar_evento(id_articulo, id_empresa, tipo: str) -> None:
    """Best-effort: un evento de telemetría nunca debe romper la navegación/compra del catálogo. Como
    mucho una fila por artículo/empresa/tipo/día (INSERT IGNORE sobre la UNIQUE de la tabla)."""
    if tipo not in ("vista", "click"):
        return
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO b2b_catalogo_eventos (id_articulo, id_empresa, tipo, fecha) "
                "VALUES (%s,%s,%s,CURDATE())", (id_articulo, id_empresa, tipo))
            conn.commit()
    except Exception as e:
        logger.debug("registrar_evento(%s,%s,%s): %s", id_articulo, id_empresa, tipo, e)


def metricas_de_suministrador(id_suministrador, *, dias: int = 30) -> list[dict]:
    """[{codigo, nombre, vistas, clics}] de los últimos `dias` días, artículos más vistos primero."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.codigo, c.nombre, "
                "COALESCE(SUM(e.tipo='vista'),0) AS vistas, "
                "COALESCE(SUM(e.tipo='click'),0) AS clics "
                "FROM b2b_catalogo c LEFT JOIN b2b_catalogo_eventos e "
                "ON e.id_articulo = c.id AND e.fecha >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
                "WHERE c.id_suministrador=%s "
                "GROUP BY c.id, c.codigo, c.nombre ORDER BY vistas DESC, clics DESC",
                (int(dias), id_suministrador))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("metricas_de_suministrador(%s): %s", id_suministrador, e)
        return []


# ── Cross-sell: "comprados juntos habitualmente" ─────────────────────────────
def _sector_ids_visibles(id_empresa) -> set:
    """Sectores visibles para `id_empresa` (propio + compatibles) — mismo criterio de aislamiento que
    `buscar_para_empresa`, resuelto aquí a partir de `empresas.sector_id` porque este módulo no recibe
    la sesión ya resuelta (a diferencia del portal, que ya tiene `ses['sector_id']`)."""
    try:
        from src.services.compras import sectores
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT sector_id FROM empresas WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            sector_id = (row[0] if row and not isinstance(row, dict) else (row or {}).get("sector_id"))
        return sectores.compatibles_de(sector_id) if sector_id else set()
    except Exception as e:
        logger.error("_sector_ids_visibles(%s): %s", id_empresa, e)
        return set()


def productos_relacionados(codigo_articulo, id_empresa, limite: int = 5) -> list[dict]:
    """"Comprados juntos habitualmente": otros artículos que aparecen con más frecuencia en el MISMO
    pedido B2B (`transaccion_lineas`/`transaccion_comercial`, origen='b2b') que `codigo_articulo`, a
    través del histórico REAL de pedidos de todas las empresas (la co-ocurrencia es una señal de
    mercado, no privada de una empresa) — nunca una sugerencia inventada/aleatoria. Si el artículo no
    tiene ningún pedido real todavía (cold start), devuelve una lista vacía honesta en vez de adivinar.

    El resultado se filtra a artículos activos y visibles para `id_empresa` (mismo aislamiento por
    sector que `buscar_para_empresa`) — nunca se recomienda un artículo que la empresa ni siquiera
    podría comprar."""
    codigo_articulo = str(codigo_articulo or "").strip()
    if not codigo_articulo or not id_empresa:
        return []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Estados validados reutilizados de `b2b_presupuesto` (mismo criterio que
            # `b2b_rappels.gasto_acumulado`: solo pedidos que de verdad llegaron a confirmarse cuentan
            # como señal de co-ocurrencia, un BORRADOR no es un pedido real).
            from src.services.compras.b2b_presupuesto import _ESTADOS_VALIDADOS
            placeholders = ",".join(["%s"] * len(_ESTADOS_VALIDADOS))
            cur.execute(
                f"SELECT tl2.codigo_articulo AS codigo, COUNT(DISTINCT tl1.id_tx) AS frecuencia "
                f"FROM transaccion_lineas tl1 "
                f"JOIN transaccion_comercial tc ON tc.id_tx = tl1.id_tx "
                f"JOIN transaccion_lineas tl2 ON tl2.id_tx = tl1.id_tx "
                f"AND tl2.codigo_articulo <> tl1.codigo_articulo "
                f"WHERE tl1.codigo_articulo = %s AND tc.origen='b2b' "
                f"AND tc.estado IN ({placeholders}) "
                f"GROUP BY tl2.codigo_articulo ORDER BY frecuencia DESC LIMIT %s",
                [codigo_articulo, *_ESTADOS_VALIDADOS, int(limite) * 4])
            candidatos = _filas(cur)
        if not candidatos:
            return []
        sector_ids = _sector_ids_visibles(id_empresa)
        if not sector_ids:
            return []
        codigos = [c["codigo"] for c in candidatos]
        placeholders_cod = ",".join(["%s"] * len(codigos))
        with obtener_conexion() as conn, conn.cursor() as cur:
            placeholders_sec = ",".join(["%s"] * len(sector_ids))
            cur.execute(
                f"SELECT c.*, s.razon_social AS proveedor_nombre FROM b2b_catalogo c "
                f"JOIN suministradores s ON s.id = c.id_suministrador "
                f"WHERE c.activo=1 AND c.codigo IN ({placeholders_cod}) "
                f"AND c.sector_id IN ({placeholders_sec})",
                [*codigos, *sector_ids])
            visibles = {a["codigo"]: a for a in _filas(cur)}
        orden_frecuencia = {c["codigo"]: c["frecuencia"] for c in candidatos}
        resultado = [visibles[cod] for cod in codigos if cod in visibles]
        resultado.sort(key=lambda a: orden_frecuencia.get(a["codigo"], 0), reverse=True)
        return resultado[:int(limite)]
    except Exception as e:
        logger.error("productos_relacionados(%s,%s): %s", codigo_articulo, id_empresa, e)
        return []


def importar_lote(id_suministrador, filas: list[dict], *, archivo_nombre: str | None = None) -> dict:
    """Alta masiva. `filas` = [{codigo, nombre, unidad_medida, moq, precio_unitario, descripcion?,
    es_perecedero?, lote?, fecha_caducidad?}, ...] ya parseadas por la vista. Cada fila se valida de
    forma independiente (una fila inválida no aborta el resto) y el resultado se audita en
    `b2b_catalogo_import_lotes` para que el proveedor vea exactamente qué se importó y qué no."""
    ok, errores = 0, []
    for i, fila in enumerate(filas, start=1):
        es_perecedero = str(fila.get("es_perecedero") or "").strip().lower() in ("1", "si", "sí", "true")
        # `exigir_atributos=True`: este es el ÚNICO llamante real de `importar_lote` (el alta
        # masiva del portal de proveedores), así que activa aquí la exigencia OPT-IN de
        # Talla/Marca/Color que vive en `_validar` — sin afectar a otros llamantes de
        # `crear_articulo` (tests, altas internas) que no la activan.
        r = crear_articulo(
            id_suministrador, fila.get("codigo"), fila.get("nombre"),
            unidad_medida=str(fila.get("unidad_medida") or "").strip().lower(),
            moq=fila.get("moq", 1), precio_unitario=fila.get("precio_unitario", 0),
            descripcion=fila.get("descripcion"), es_perecedero=es_perecedero,
            lote=fila.get("lote"), fecha_caducidad=fila.get("fecha_caducidad"),
            talla=fila.get("talla"), marca=fila.get("marca"), color=fila.get("color"),
            exigir_atributos=True)
        if r.get("ok"):
            ok += 1
        else:
            errores.append({"fila": i, "codigo": fila.get("codigo"), "error": r.get("error")})
    try:
        import json
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_catalogo_import_lotes (id_suministrador, archivo_nombre, filas_ok, "
                "filas_error, detalle_errores) VALUES (%s,%s,%s,%s,%s)",
                (id_suministrador, archivo_nombre, ok, len(errores),
                 json.dumps(errores, ensure_ascii=False) if errores else None))
            lote_id = cur.lastrowid
            conn.commit()
    except Exception as e:
        logger.error("importar_lote registro auditoría: %s", e)
        lote_id = None
    return {"ok": True, "lote_id": lote_id, "filas_ok": ok, "filas_error": len(errores), "errores": errores}
