import logging

from .conexion import obtener_conexion

logger = logging.getLogger("reabastecimiento_db")


def _emp(id_empresa=None):
    """Empresa activa (INV.5.2: aislamiento multiempresa de reabastecimiento)."""
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


# ── CONFIG ──────────────────────────────────────────────────────────────────

def listar_config(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rc.codigo, a.nombre,
                           COALESCE(a.Stock_tienda,0) + COALESCE(a.Stock_total,0) AS stock_actual,
                           rc.umbral_min, rc.stock_objetivo,
                           rc.origen, rc.automatico
                    FROM reab_config rc
                    JOIN articulos a ON a.codigo = rc.codigo
                    WHERE rc.id_empresa = %s
                    ORDER BY a.nombre ASC
                """, (id_empresa,))
                rows = cur.fetchall()
                return [
                    {
                        "codigo": r[0], "nombre": r[1], "stock_actual": r[2],
                        "umbral_min": r[3], "stock_objetivo": r[4],
                        "origen": r[5], "automatico": bool(r[6]),
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"Error listando config reabastecimiento: {e}")
        return []


def upsert_config(codigo: str, umbral_min: int, stock_objetivo: int,
                  origen: str = "ALMACÉN CENTRAL", automatico: bool = True,
                  id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reab_config (codigo, umbral_min, stock_objetivo, origen, automatico, id_empresa)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        umbral_min = VALUES(umbral_min),
                        stock_objetivo = VALUES(stock_objetivo),
                        origen = VALUES(origen),
                        automatico = VALUES(automatico),
                        id_empresa = VALUES(id_empresa)
                """, (codigo, umbral_min, stock_objetivo, origen, int(automatico), id_empresa))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error guardando config reabastecimiento: {e}")
        return False


def set_almacenes_reab(codigo: str, id_almacen_origen=None, id_almacen_destino=None) -> bool:
    """INV.4.7: asocia almacén origen/destino reales a la config de reabastecimiento
    (referencia a `almacen`), sustituyendo el origen de texto libre. Aditivo: no toca el
    resto de la configuración ni la IA."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE reab_config SET id_almacen_origen=%s, id_almacen_destino=%s "
                        "WHERE codigo=%s", (id_almacen_origen, id_almacen_destino, codigo))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"set_almacenes_reab({codigo}): {e}")
        return False


def propuestas_por_almacen(id_almacen, id_empresa=None) -> list:
    """INV.4.7: artículos bajo umbral con disponibilidad real en un almacén (stock_almacen)."""
    try:
        from src.db.empresa import empresa_actual_id
        id_empresa = id_empresa or empresa_actual_id()
    except Exception:
        id_empresa = id_empresa
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT rc.codigo, a.nombre, COALESCE(sa.cantidad,0) AS stock_almacen,
                       rc.umbral_min, rc.stock_objetivo
                FROM reab_config rc
                JOIN articulos a ON a.codigo=rc.codigo
                LEFT JOIN stock_almacen sa ON sa.codigo_articulo=rc.codigo
                       AND sa.id_almacen=%s AND sa.id_empresa=%s
                WHERE COALESCE(sa.cantidad,0) < rc.umbral_min
                ORDER BY a.nombre
            """, (id_almacen, id_empresa))
            return [{"codigo": r[0], "nombre": r[1], "stock_almacen": r[2],
                     "umbral_min": r[3], "stock_objetivo": r[4]}
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"propuestas_por_almacen: {e}")
        return []


def eliminar_config(codigo: str, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reab_config WHERE codigo=%s AND id_empresa=%s",
                            (codigo, id_empresa))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error eliminando config reabastecimiento: {e}")
        return False


def obtener_config(codigo: str, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT umbral_min, stock_objetivo, origen, automatico "
                    "FROM reab_config WHERE codigo=%s AND id_empresa=%s",
                    (codigo, id_empresa)
                )
                r = cur.fetchone()
                if r:
                    return {"umbral_min": r[0], "stock_objetivo": r[1],
                            "origen": r[2], "automatico": bool(r[3])}
    except Exception as e:
        logger.error(f"Error obteniendo config: {e}")
    return None


# ── PROPUESTAS ───────────────────────────────────────────────────────────────

def crear_propuesta(codigo: str, nombre: str, cantidad: int,
                    origen: str, stock_actual: int, stock_objetivo: int,
                    id_empresa=None, id_almacen=None, id_almacen_origen=None,
                    id_almacen_destino=None, prevision_usada=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reab_propuestas
                        (codigo, nombre_articulo, cantidad, origen, stock_actual,
                         stock_objetivo, estado, id_empresa, id_almacen,
                         id_almacen_origen, id_almacen_destino, prevision_usada)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, %s, %s, %s)
                """, (codigo, nombre, cantidad, origen, stock_actual, stock_objetivo, id_empresa,
                      id_almacen, id_almacen_origen, id_almacen_destino, prevision_usada))
                pid = cur.lastrowid
            conn.commit()
            return pid
    except Exception as e:
        logger.error(f"Error creando propuesta: {e}")
    return None


def listar_propuestas(estados: tuple = None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                if estados:
                    placeholders = ",".join(["%s"] * len(estados))
                    cur.execute(
                        f"SELECT id, codigo, nombre_articulo, cantidad, origen, "
                        f"stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                        f"FROM reab_propuestas WHERE estado IN ({placeholders}) AND id_empresa=%s "
                        f"ORDER BY fecha_creacion DESC",
                        (*estados, id_empresa)
                    )
                else:
                    cur.execute(
                        "SELECT id, codigo, nombre_articulo, cantidad, origen, "
                        "stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                        "FROM reab_propuestas WHERE id_empresa=%s ORDER BY fecha_creacion DESC",
                        (id_empresa,)
                    )
                rows = cur.fetchall()
                return [
                    {
                        "id": r[0], "codigo": r[1], "nombre": r[2],
                        "cantidad": r[3], "origen": r[4],
                        "stock_actual": r[5], "stock_objetivo": r[6],
                        "estado": r[7], "fecha_creacion": r[8], "fecha_accion": r[9],
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"Error listando propuestas: {e}")
        return []


def cambiar_estado_propuesta(propuesta_id: int, nuevo_estado: str) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE reab_propuestas SET estado=%s, fecha_accion=NOW() WHERE id=%s",
                    (nuevo_estado, propuesta_id)
                )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error cambiando estado propuesta: {e}")
        return False


def marcar_articulos_recibidos(codigos: list, id_empresa=None) -> int:
    """Cambia a 'recibido' todas las propuestas activas de los artículos indicados."""
    if not codigos:
        return 0
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(codigos))
                cur.execute(
                    f"UPDATE reab_propuestas SET estado='recibido', fecha_accion=NOW() "
                    f"WHERE codigo IN ({placeholders}) AND id_empresa=%s "
                    f"AND estado IN ('pendiente','aprobado','enviado')",
                    (*codigos, id_empresa),
                )
                count = cur.rowcount
            conn.commit()
            return count
    except Exception as e:
        logger.error(f"Error marcando artículos como recibidos: {e}")
        return 0


def propuesta_pendiente_existe(codigo: str, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM reab_propuestas "
                    "WHERE codigo=%s AND id_empresa=%s AND estado IN ('pendiente','aprobado','enviado')",
                    (codigo, id_empresa)
                )
                r = cur.fetchone()
                return bool(r and r[0] > 0)
    except Exception as e:
        logger.error(f"Error comprobando propuesta existente: {e}")
    return False


def obtener_propuesta(propuesta_id: int) -> dict | None:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, codigo, nombre_articulo, cantidad, origen, "
                    "stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                    "FROM reab_propuestas WHERE id=%s",
                    (propuesta_id,)
                )
                r = cur.fetchone()
                if r:
                    return {
                        "id": r[0], "codigo": r[1], "nombre": r[2],
                        "cantidad": r[3], "origen": r[4],
                        "stock_actual": r[5], "stock_objetivo": r[6],
                        "estado": r[7], "fecha_creacion": r[8], "fecha_accion": r[9],
                    }
    except Exception as e:
        logger.error(f"Error obteniendo propuesta: {e}")
    return None


# ── PROGRAMACIÓN DE ENVÍOS ───────────────────────────────────────────────────

def cargar_schedule() -> dict:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT email, dias, hora, minuto, ultima_envio, smtp_user, smtp_pass "
                    "FROM reab_schedule LIMIT 1"
                )
                r = cur.fetchone()
                if r:
                    return {
                        "email": r[0] or "", "dias": r[1] or "",
                        "hora": int(r[2]), "minuto": int(r[3]),
                        "ultima_envio": r[4],
                        "smtp_user": r[5] or "", "smtp_pass": r[6] or "",
                    }
    except Exception as e:
        logger.error(f"Error cargando schedule: {e}")
    return {"email": "", "dias": "", "hora": 8, "minuto": 0, "ultima_envio": None,
            "smtp_user": "", "smtp_pass": ""}


def guardar_schedule(email: str, dias: str, hora: int, minuto: int,
                     smtp_user: str = "", smtp_pass: str = "") -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM reab_schedule LIMIT 1")
                r = cur.fetchone()
                if r:
                    cur.execute(
                        "UPDATE reab_schedule SET email=%s, dias=%s, hora=%s, minuto=%s, "
                        "smtp_user=%s, smtp_pass=%s WHERE id=%s",
                        (email, dias, hora, minuto, smtp_user, smtp_pass, r[0])
                    )
                else:
                    cur.execute(
                        "INSERT INTO reab_schedule (email, dias, hora, minuto, smtp_user, smtp_pass) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (email, dias, hora, minuto, smtp_user, smtp_pass)
                    )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error guardando schedule: {e}")
        return False


def marcar_envio_hoy() -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE reab_schedule SET ultima_envio = CURDATE()")
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error marcando envio: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# INV.6 — REABASTECIMIENTO AVANZADO POR ALMACÉN
# ════════════════════════════════════════════════════════════════════════════

def set_parametros_avanzados(codigo: str, stock_maximo: int = None, punto_pedido: int = None,
                             lead_time_dias: int = None, id_proveedor_preferente=None,
                             id_empresa=None) -> bool:
    """INV.6.1: define stock máximo, punto de pedido, lead time y proveedor preferente
    de un artículo (solo actualiza los campos indicados). Requiere config existente."""
    id_empresa = _emp(id_empresa)
    sets, params = [], []
    for col, val in (("stock_maximo", stock_maximo), ("punto_pedido", punto_pedido),
                     ("lead_time_dias", lead_time_dias),
                     ("id_proveedor_preferente", id_proveedor_preferente)):
        if val is not None:
            sets.append(f"{col}=%s"); params.append(val)
    if not sets:
        return False
    params += [codigo, id_empresa]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE reab_config SET {', '.join(sets)} WHERE codigo=%s AND id_empresa=%s",
                        params)
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"set_parametros_avanzados({codigo}): {e}")
        return False


def obtener_config_avanzada(codigo: str, id_empresa=None) -> dict | None:
    """Config completa de reabastecimiento (umbral/objetivo + max/punto/lead/proveedor)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT umbral_min, stock_objetivo, stock_maximo, punto_pedido, "
                        "lead_time_dias, id_proveedor_preferente, id_almacen_origen, "
                        "id_almacen_destino, automatico FROM reab_config "
                        "WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            return {"umbral_min": r[0], "stock_objetivo": r[1], "stock_maximo": r[2],
                    "punto_pedido": r[3], "lead_time_dias": r[4],
                    "id_proveedor_preferente": r[5], "id_almacen_origen": r[6],
                    "id_almacen_destino": r[7], "automatico": bool(r[8])}
    except Exception as e:
        logger.error(f"obtener_config_avanzada({codigo}): {e}")
        return None


def _prevision_demanda(codigo: str, dias: int, prevision_fn=None) -> int:
    """Previsión de demanda (INV.6.3) sobre `dias`. Best-effort: usa `prevision_fn` si se
    inyecta (p.ej. Prophet); si no hay previsión disponible, devuelve 0 (no altera el
    comportamiento base por punto de pedido)."""
    if not dias or dias <= 0:
        return 0
    try:
        if prevision_fn is not None:
            return max(0, int(prevision_fn(codigo, dias) or 0))
        # CMP.7: servicio de previsión desacoplado por defecto (no depende de main.py).
        from src.db import prevision
        return max(0, int(prevision.prevision_demanda(codigo, dias) or 0))
    except Exception as e:
        logger.warning("prevision IA no disponible para %s: %s", codigo, e)
    return 0


def generar_propuestas_almacen(id_almacen, id_empresa=None, usar_ia=True, prevision_fn=None) -> list:
    """INV.6.2/6.3/6.4: genera propuestas de reposición para un almacén usando stock_almacen
    (NO la caché). Regla: si stock_actual < punto_pedido_efectivo → proponer
    (stock_maximo - stock_actual). punto_pedido_efectivo = max(punto_pedido, previsión IA
    sobre lead_time). Persiste cada propuesta con almacén origen/destino y previsión.
    Devuelve la lista de ids de propuesta creados."""
    from src.db import stock_almacen as SA
    id_empresa = _emp(id_empresa)
    creados = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT rc.codigo, a.nombre, rc.umbral_min, rc.stock_objetivo, "
                        "rc.stock_maximo, rc.punto_pedido, rc.lead_time_dias, rc.id_almacen_origen, "
                        "rc.id_proveedor_preferente "
                        "FROM reab_config rc JOIN articulos a ON a.codigo=rc.codigo "
                        "WHERE rc.id_empresa=%s", (id_empresa,))
            filas = cur.fetchall()
        for r in filas:
            codigo, nombre, umbral, objetivo, maximo, punto, lead, alm_orig, id_prov = r
            punto = punto or umbral or 0
            maximo = maximo or objetivo or 0
            # CMP.7: lead time del PROVEEDOR preferente con fallback a reab_config.
            if (not lead) and id_prov:
                try:
                    from src.db import proveedores
                    lead = (proveedores.condiciones_comerciales(id_prov, id_empresa) or {}).get("lead_time_dias") or 0
                except Exception:
                    pass
            stock_actual = SA.obtener_stock_almacen(codigo, id_almacen, id_empresa)
            prevision = _prevision_demanda(codigo, lead or 0, prevision_fn) if usar_ia else 0
            punto_efectivo = max(int(punto), int(prevision))
            if stock_actual < punto_efectivo and not propuesta_pendiente_existe(codigo, id_empresa):
                cantidad = max(0, int(maximo) - int(stock_actual))
                if cantidad <= 0:
                    continue
                pid = crear_propuesta(codigo, nombre or codigo, cantidad, "ALMACÉN",
                                      stock_actual, maximo, id_empresa=id_empresa,
                                      id_almacen=id_almacen, id_almacen_origen=alm_orig,
                                      id_almacen_destino=id_almacen, prevision_usada=prevision)
                if pid:
                    creados.append(pid)
        return creados
    except Exception as e:
        logger.error(f"generar_propuestas_almacen({id_almacen}): {e}")
        return creados


def generar_pedidos_compra(propuesta_ids=None, usuario=None, id_empresa=None) -> list:
    """INV.6.4: convierte propuestas en pedidos de compra (reutiliza compras.E2.7),
    agrupando por proveedor preferente cuando existe. Devuelve ids de pedido creados."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db import compras
    except Exception as e:
        logger.error("compras no disponible: %s", e)
        return []
    props = listar_propuestas(("pendiente",), id_empresa=id_empresa)
    if propuesta_ids is not None:
        ids = set(propuesta_ids)
        props = [p for p in props if p["id"] in ids]
    if not props:
        return []
    # Agrupa por proveedor preferente del artículo (None → grupo general).
    grupos = {}
    for p in props:
        cfg = obtener_config_avanzada(p["codigo"], id_empresa) or {}
        grupos.setdefault(cfg.get("id_proveedor_preferente"), []).append(p["id"])
    pedidos = []
    for proveedor, pid_list in grupos.items():
        ped = compras.crear_pedido_desde_propuestas(propuesta_ids=pid_list,
                                                    id_proveedor=proveedor, usuario=usuario,
                                                    id_empresa=id_empresa)
        if ped:
            pedidos.append(ped)
    return pedidos


def ejecutar_aprovisionamiento(id_empresa=None, id_almacen=None, crear_pedidos=False,
                               usuario=None, usar_ia=True) -> dict:
    """CMP.7 — Scheduler de aprovisionamiento: genera propuestas para todos los almacenes
    (o uno concreto) de la empresa y, opcionalmente, crea los pedidos de compra agrupados
    por proveedor preferente. Devuelve {propuestas, pedidos}."""
    id_empresa = _emp(id_empresa)
    propuestas = []
    try:
        from src.db import stock_almacen as SA
        almacenes = ([{"id": id_almacen}] if id_almacen
                     else SA.listar_almacenes(id_empresa))
        for a in almacenes:
            aid = a.get("id") if isinstance(a, dict) else a
            if aid:
                propuestas += generar_propuestas_almacen(aid, id_empresa=id_empresa, usar_ia=usar_ia)
    except Exception as e:
        logger.error("ejecutar_aprovisionamiento: %s", e)
    pedidos = []
    if crear_pedidos and propuestas:
        pedidos = generar_pedidos_compra(propuesta_ids=propuestas, usuario=usuario,
                                         id_empresa=id_empresa)
    return {"propuestas": propuestas, "pedidos": pedidos}
