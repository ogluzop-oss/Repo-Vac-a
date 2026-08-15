"""Capa de datos del MAPA de tienda y las UBICACIONES de artículos (pantalla `gui/ubicacion_tienda`).

Fase 3 · cliente fino: extraído de `gui/ubicacion_tienda` para que la ventana (un lienzo interactivo de
~13k líneas) no ejecute SQL directo. Cubre DOS dominios:

- **PLANO / MAPA** (`configuracion_mapa`): imagen del plano por planta, calibración (escala/ancla),
  altura, tipo/título, muros y puntos de infraestructura.
- **UBICACIONES** (`ubicaciones`): puntos físicos de artículos y marcadores RFID (EPC), coordenadas de
  mapa, verificación e impresión de etiquetas.

La GUI solo orquesta el lienzo; aquí viven las consultas. Se preserva el SQL original (mismas columnas y
semántica) para no cambiar el comportamiento. Los accesos a `articulos` reutilizan la PK compuesta
(empresa, código) de la migr 0181.
"""

import json
import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("ubicaciones.db")


def _emp():
    """id_empresa ACTIVO (o None si no hay sesión) para filtrar `articulos` (PK compuesta, migr 0181)."""
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# PLANO / MAPA  (tabla configuracion_mapa)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def ensure_schema_mapa():
    """Columnas defensivas para BDs antiguas (idempotente; no falla si ya existen)."""
    ddl = (
        "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS altura_metros DOUBLE DEFAULT NULL",
        "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS titulo_plano VARCHAR(255) DEFAULT NULL",
        "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'LOCAL'",
    )
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for sql in ddl:
                try:
                    cur.execute(sql)
                except Exception:
                    pass
            conn.commit()
    except Exception:
        pass


def plano_info(planta_index):
    """(tipo, titulo) del plano de la planta, o None si no existe."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(tipo,'LOCAL'), titulo_plano FROM configuracion_mapa "
                        "WHERE planta_index=%s", (planta_index,))
            r = cur.fetchone()
            return (r[0], r[1]) if r else None
    except Exception:
        return None


def plano_info_completo(planta_index):
    """(tipo, titulo, ruta_imagen) del plano de la planta, o None si no existe."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(tipo,'LOCAL'), titulo_plano, ruta_imagen FROM configuracion_mapa "
                        "WHERE planta_index=%s", (planta_index,))
            r = cur.fetchone()
            return (r[0], r[1], r[2]) if r else None
    except Exception:
        return None


def ruta_imagen(planta_index):
    """Ruta de imagen del plano de la planta, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ruta_imagen FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            r = cur.fetchone()
            return r[0] if r else None
    except Exception:
        return None


def esta_calibrada(planta_index) -> bool:
    """True si la planta tiene escala_px_metro > 0 (plano calibrado)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT escala_px_metro FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            r = cur.fetchone()
            return r is not None and float(r[0] or 0) > 0
    except Exception:
        return False


def existe_planta(planta_index) -> bool:
    """True si hay un registro de configuración para la planta."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            r = cur.fetchone()
            return bool(r and r[0] > 0)
    except Exception:
        return False


def max_planta_con_imagen():
    """Índice de planta MÁS ALTO que tiene imagen cargada, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT MAX(planta_index) FROM configuracion_mapa "
                        "WHERE ruta_imagen IS NOT NULL AND ruta_imagen != ''")
            r = cur.fetchone()
            return r[0] if r and r[0] is not None else None
    except Exception:
        return None


def primera_planta_con_imagen():
    """Índice de planta MÁS BAJO que tiene imagen cargada, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT planta_index FROM configuracion_mapa "
                        "WHERE ruta_imagen IS NOT NULL AND ruta_imagen != '' "
                        "ORDER BY planta_index ASC LIMIT 1")
            r = cur.fetchone()
            return int(r[0]) if r else None
    except Exception:
        return None


def guardar_altura(planta_index, metros):
    """Persiste la altura (metros) del plano; asegura la columna. Devuelve `metros`."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE configuracion_mapa "
                            "ADD COLUMN IF NOT EXISTS altura_metros DOUBLE DEFAULT NULL")
            except Exception:
                pass
            cur.execute("UPDATE configuracion_mapa SET altura_metros=%s WHERE planta_index=%s",
                        (metros, planta_index))
            conn.commit()
    except Exception as e:
        logger.error("guardar_altura(%s): %s", planta_index, e)
    return metros


def reset_calibracion(planta_index):
    """Borra la calibración de la planta (escala/ancla/matriz/muros) manteniendo el registro."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE configuracion_mapa "
                        "SET escala_px_metro=0, ancla_x=0, ancla_y=0, "
                        "    matriz_binaria=NULL, muros_vectoriales='[]' "
                        "WHERE planta_index=%s", (planta_index,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("reset_calibracion(%s): %s", planta_index, e)
        return False


def puntos_infraestructura(planta_index) -> list:
    """Lista (deserializada de JSON) de puntos de infraestructura de la planta; [] si no hay."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT puntos_infraestructura FROM configuracion_mapa WHERE planta_index=%s",
                        (planta_index,))
            r = cur.fetchone()
            if r and r[0]:
                try:
                    return json.loads(r[0])
                except Exception:
                    return []
            return []
    except Exception:
        return []


def guardar_puntos_infraestructura(planta_index, lista) -> bool:
    """Upsert de la lista de puntos de infraestructura (se serializa a JSON)."""
    payload = json.dumps(lista)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            if cur.fetchone():
                cur.execute("UPDATE configuracion_mapa SET puntos_infraestructura=%s WHERE planta_index=%s",
                            (payload, planta_index))
            else:
                cur.execute("INSERT INTO configuracion_mapa (planta_index, puntos_infraestructura) "
                            "VALUES (%s, %s)", (planta_index, payload))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_puntos_infraestructura(%s): %s", planta_index, e)
        return False


def guardar_calibracion(planta_index, escala, ancla_x, ancla_y, ruta_imagen) -> bool:
    """Upsert de la calibración de la planta (escala, ancla y ruta de imagen)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            if cur.fetchone():
                cur.execute("UPDATE configuracion_mapa "
                            "SET escala_px_metro=%s, ancla_x=%s, ancla_y=%s, ruta_imagen=%s, "
                            "    fecha_actualizacion=NOW() WHERE planta_index=%s",
                            (escala, ancla_x, ancla_y, ruta_imagen, planta_index))
            else:
                cur.execute("INSERT INTO configuracion_mapa "
                            "(planta_index, escala_px_metro, ancla_x, ancla_y, ruta_imagen, fecha_actualizacion) "
                            "VALUES (%s, %s, %s, %s, %s, NOW())",
                            (planta_index, escala, ancla_x, ancla_y, ruta_imagen))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_calibracion(%s): %s", planta_index, e)
        return False


def guardar_plano_completo(planta_index, ruta_imagen_nueva, matriz_binaria, escala,
                           muros_json, infra_json, ancla_x, ancla_y):
    """Upsert del plano completo. Si `ruta_imagen_nueva` es vacía, conserva la ruta ya guardada.
    Devuelve la ruta de imagen EFECTIVA finalmente persistida."""
    ruta = ruta_imagen_nueva
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ruta_imagen FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            reg = cur.fetchone()
            if not ruta and reg and reg[0]:
                ruta = reg[0]
            if reg:
                cur.execute(
                    "UPDATE configuracion_mapa SET "
                    "ruta_imagen=%s, matriz_binaria=%s, escala_px_metro=%s, "
                    "muros_vectoriales=%s, puntos_infraestructura=%s, "
                    "ancla_x=%s, ancla_y=%s, fecha_actualizacion=NOW() WHERE planta_index=%s",
                    (ruta, matriz_binaria, escala, muros_json, infra_json, ancla_x, ancla_y, planta_index))
            else:
                cur.execute(
                    "INSERT INTO configuracion_mapa "
                    "(planta_index, ruta_imagen, matriz_binaria, escala_px_metro, "
                    "muros_vectoriales, puntos_infraestructura, ancla_x, ancla_y, fecha_actualizacion) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
                    (planta_index, ruta, matriz_binaria, escala, muros_json, infra_json, ancla_x, ancla_y))
            conn.commit()
    except Exception as e:
        logger.error("guardar_plano_completo(%s): %s", planta_index, e)
    return ruta


def registrar_plano(planta_index, ruta_imagen_nombre, titulo_plano, tipo_plano) -> bool:
    """Upsert al CARGAR un plano (imagen): registra ruta/título/tipo y resetea la escala a 0.
    Asegura las columnas título/tipo para BDs antiguas."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for alter in (
                "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS titulo_plano VARCHAR(255) DEFAULT NULL",
                "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'LOCAL'",
            ):
                try:
                    cur.execute(alter)
                except Exception:
                    pass
            cur.execute(
                "INSERT INTO configuracion_mapa "
                "(planta_index, ruta_imagen, titulo_plano, tipo, escala_px_metro, fecha_actualizacion) "
                "VALUES (%s, %s, %s, %s, 0, NOW()) "
                "ON DUPLICATE KEY UPDATE ruta_imagen=VALUES(ruta_imagen), "
                "titulo_plano=COALESCE(VALUES(titulo_plano), titulo_plano), "
                "tipo=COALESCE(VALUES(tipo), tipo), escala_px_metro=0",
                (planta_index, ruta_imagen_nombre, titulo_plano, tipo_plano))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_plano(%s): %s", planta_index, e)
        return False


def eliminar_planta(planta_index) -> bool:
    """Borra la configuración de plano de la planta."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM configuracion_mapa WHERE planta_index=%s", (planta_index,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("eliminar_planta(%s): %s", planta_index, e)
        return False


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# UBICACIONES  (tabla ubicaciones)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def ubicacion_por_articulo(codigo):
    """(mapa_x, mapa_y, verificado, pasillo, estanteria) del artículo, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT mapa_x, mapa_y, verificado, pasillo, estanteria "
                        "FROM ubicaciones WHERE codigo_articulo=%s", (codigo,))
            return cur.fetchone()
    except Exception:
        return None


def nombre_y_coords_por_articulo(codigo):
    """(nombre, mapa_x, mapa_y) del punto de ubicación del artículo, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, mapa_x, mapa_y FROM ubicaciones WHERE codigo_articulo=%s", (codigo,))
            return cur.fetchone()
    except Exception:
        return None


def coords_por_articulo(codigo):
    """(mapa_x, mapa_y) del artículo, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT mapa_x, mapa_y FROM ubicaciones WHERE codigo_articulo=%s", (codigo,))
            return cur.fetchone()
    except Exception:
        return None


def coords_por_pasillo_estanteria(pasillo, estanteria):
    """(mapa_x, mapa_y) de la mejor estantería que coincide con pasillo+estantería, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT mapa_x, mapa_y FROM ubicaciones "
                "WHERE pasillo=%s AND estanteria=%s "
                "  AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL AND (mapa_x != 0 OR mapa_y != 0) "
                "ORDER BY (codigo_articulo IS NULL OR codigo_articulo = '') DESC, verificado DESC, id DESC "
                "LIMIT 1", (pasillo, estanteria))
            return cur.fetchone()
    except Exception:
        return None


def articulos_ubicados() -> list:
    """Lista de códigos de artículo con coordenada de mapa asignada (mapa_x != 0)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_articulo FROM ubicaciones WHERE mapa_x != 0")
            return [row[0] for row in cur.fetchall()]
    except Exception:
        return []


def epcs_sin_imprimir() -> list:
    """[(epc, pasillo, estanteria)] de ubicaciones aún no impresas (cola de etiquetas RFID)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT epc, pasillo, estanteria FROM ubicaciones WHERE impreso = 0")
            return list(cur.fetchall())
    except Exception:
        return []


def marcar_epcs_impresos(epcs) -> None:
    """Marca `impreso = 1` las ubicaciones cuyos EPC se pasan (iterable)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for epc in epcs:
                cur.execute("UPDATE ubicaciones SET impreso = 1 WHERE epc = %s", (epc,))
            conn.commit()
    except Exception as e:
        logger.error("marcar_epcs_impresos: %s", e)


def eliminar_por_epc(epc) -> bool:
    """Borra la ubicación (marcador) con ese EPC."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ubicaciones WHERE epc = %s", (epc,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("eliminar_por_epc(%s): %s", epc, e)
        return False


def upsert_satelite(epc, nombre, x, y, real_x, real_y) -> bool:
    """Upsert de un nodo SATÉLITE de infraestructura (pasillo fijo 'SISTEMA')."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ubicaciones "
                "(epc, pasillo, estanteria, mapa_x, mapa_y, real_x, real_y, verificado) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE estanteria=%s, real_x=%s, real_y=%s, mapa_x=%s, mapa_y=%s",
                (epc, "SISTEMA", nombre, x, y, real_x, real_y, nombre, real_x, real_y, x, y))
            conn.commit()
        return True
    except Exception as e:
        logger.error("upsert_satelite(%s): %s", epc, e)
        return False


def upsert_nodo_qr(qr_id, pasillo, estanteria, x, y) -> bool:
    """Upsert de un nodo QR de estantería (verificado=1)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ubicaciones "
                "(codigo_articulo, pasillo, estanteria, balda, mapa_x, mapa_y, verificado) "
                "VALUES (%s, %s, %s, '0', %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE mapa_x=VALUES(mapa_x), mapa_y=VALUES(mapa_y), verificado=1",
                (qr_id, pasillo, estanteria, x, y))
            conn.commit()
        return True
    except Exception as e:
        logger.error("upsert_nodo_qr(%s): %s", qr_id, e)
        return False


def flush_iconos(iconos) -> int:
    """Vuelca una lista de iconos pendientes a `ubicaciones` (upsert por EPC). Cada icono es un dict con
    epc/pasillo/estanteria/mapa_x/mapa_y/real_x/real_y. Devuelve cuántos se procesaron."""
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for ico in iconos:
                cur.execute(
                    "INSERT INTO ubicaciones "
                    "(epc, pasillo, estanteria, mapa_x, mapa_y, real_x, real_y, verificado, fecha_actualizacion) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW()) "
                    "ON DUPLICATE KEY UPDATE mapa_x=VALUES(mapa_x), mapa_y=VALUES(mapa_y), "
                    "real_x=VALUES(real_x), real_y=VALUES(real_y), estanteria=VALUES(estanteria), "
                    "fecha_actualizacion=NOW()",
                    (ico["epc"], ico["pasillo"], ico["estanteria"],
                     ico["mapa_x"], ico["mapa_y"], ico["real_x"], ico["real_y"]))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("flush_iconos: %s", e)
    return n


def asignar_ubicacion(codigo, pasillo, estanteria, nivel, es_lineal) -> dict:
    """Transacción completa de asignación de ubicación de un artículo:

    1) Actualiza la ubicación comercial en `articulos` (tienda LINEAL o almacén) y limpia incidencia.
    2) Busca coordenadas de mapa de esa estantería en `ubicaciones`.
    3) Upsert del artículo en `ubicaciones` (tabla técnica) con esas coordenadas.
    4) Si hay coordenadas, las sincroniza también en `articulos`.

    Devuelve {ok, con_coordenadas, mapa_x, mapa_y}.
    """
    emp = _emp()
    ubicacion_legible = f"{pasillo}-{estanteria}-{nivel}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if es_lineal:
                cur.execute(
                    "UPDATE articulos SET pasillo=%s, estanteria=%s, nivel=%s, ubicacion_tienda=%s, "
                    "incidencia_ubicacion=0, ultima_actualizacion=NOW() "
                    "WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)",
                    (pasillo, estanteria, nivel, ubicacion_legible, codigo, emp, emp))
            else:
                cur.execute(
                    "UPDATE articulos SET pasillo_almacen=%s, estanteria_almacen=%s, nivel_almacen=%s, "
                    "ubicacion_almacen=%s, incidencia_ubicacion=0, ultima_actualizacion=NOW() "
                    "WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)",
                    (pasillo, estanteria, nivel, ubicacion_legible, codigo, emp, emp))

            cur.execute(
                "SELECT mapa_x, mapa_y FROM ubicaciones "
                "WHERE pasillo=%s AND estanteria=%s "
                "  AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL AND (mapa_x != 0 OR mapa_y != 0) "
                "ORDER BY (codigo_articulo IS NULL OR codigo_articulo = '') DESC, verificado DESC, id DESC "
                "LIMIT 1", (pasillo, estanteria))
            coord = cur.fetchone()
            mapa_x = float(coord[0]) if coord else None
            mapa_y = float(coord[1]) if coord else None

            cur.execute(
                "INSERT INTO ubicaciones (codigo_articulo, pasillo, estanteria, balda, mapa_x, mapa_y, verificado) "
                "VALUES (%s, %s, %s, %s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE pasillo=VALUES(pasillo), estanteria=VALUES(estanteria), "
                "balda=VALUES(balda), mapa_x=COALESCE(VALUES(mapa_x), mapa_x), "
                "mapa_y=COALESCE(VALUES(mapa_y), mapa_y), "
                "verificado=IF(COALESCE(VALUES(mapa_x), mapa_x) IS NULL "
                "AND COALESCE(VALUES(mapa_y), mapa_y) IS NULL, verificado, 1)",
                (codigo, pasillo, estanteria, nivel, mapa_x, mapa_y))

            if coord:
                cur.execute(
                    "UPDATE articulos SET mapa_x=%s, mapa_y=%s WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)",
                    (mapa_x, mapa_y, codigo, emp, emp))
            conn.commit()
        return {"ok": True, "con_coordenadas": bool(coord), "mapa_x": mapa_x, "mapa_y": mapa_y}
    except Exception as e:
        logger.error("asignar_ubicacion(%s): %s", codigo, e)
        return {"ok": False, "con_coordenadas": False, "mapa_x": None, "mapa_y": None}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ARTÍCULOS  (lecturas/escrituras propias de esta pantalla; PK compuesta empresa+código, migr 0181)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def buscar_codigo_nombre(busqueda):
    """(codigo, nombre) por código exacto y, si no, por nombre parcial; None si no hay."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre FROM articulos WHERE codigo=%s", (busqueda,))
            r = cur.fetchone()
            if not r:
                cur.execute("SELECT codigo, nombre FROM articulos WHERE nombre LIKE %s LIMIT 1",
                            (f"%{busqueda}%",))
                r = cur.fetchone()
            return r
    except Exception:
        return None


def buscar_con_ubicacion_stock(termino):
    """(codigo, nombre, ubicacion_tienda, ubicacion_almacen, stock) por nombre parcial o código exacto."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, ubicacion_tienda, ubicacion_almacen, COALESCE(Stock_total, 0) "
                "FROM articulos WHERE nombre LIKE %s OR codigo=%s", (f"%{termino}%", termino))
            return cur.fetchone()
    except Exception:
        return None


def buscar_articulo_con_ubicaciones(termino):
    """LEFT JOIN articulos+ubicaciones por término (código exacto o nombre parcial). Devuelve
    (codigo, nombre, ubicacion_tienda, pasillo, estanteria, ubicacion_almacen, pasillo_almacen,
    estanteria_almacen) o None. Pasillo/estantería viven en `ubicaciones` (migr 0105)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT a.codigo, a.nombre, a.ubicacion_tienda, u.pasillo, u.estanteria, "
                "a.ubicacion_almacen, u.pasillo_almacen, u.estanteria_almacen "
                "FROM articulos a LEFT JOIN ubicaciones u ON u.codigo_articulo = a.codigo "
                "WHERE a.codigo=%s OR a.nombre LIKE %s "
                "ORDER BY CASE WHEN a.codigo=%s THEN 0 ELSE 1 END, a.nombre ASC LIMIT 1",
                (termino, f"%{termino}%", termino))
            return cur.fetchone()
    except Exception:
        return None


def buscar_ubicaciones_por_texto(termino) -> list:
    """[(nombre_ubicacion, mapa_x, mapa_y)] de ubicaciones con coordenadas que casan con el texto
    (pasillo/estantería/balda), hasta 6 resultados. Fallback de búsqueda de destino."""
    like = f"%{termino}%"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT CONCAT_WS(' ', pasillo, estanteria, balda) AS nombre_ubicacion, mapa_x, mapa_y "
                "FROM ubicaciones WHERE ("
                "CONCAT_WS(' ', pasillo, estanteria, balda) LIKE %s "
                "OR CONCAT_WS('-', pasillo, estanteria, balda) LIKE %s "
                "OR pasillo LIKE %s OR estanteria LIKE %s) "
                "AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL AND (mapa_x != 0 OR mapa_y != 0) "
                "ORDER BY verificado DESC, id DESC LIMIT 6", (like, like, like, like))
            return list(cur.fetchall())
    except Exception:
        return []


def plantas_con_imagen() -> list:
    """Lista de índices de planta que tienen imagen cargada (para el selector de borrado)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT planta_index FROM configuracion_mapa "
                        "WHERE ruta_imagen IS NOT NULL AND ruta_imagen != '' "
                        "GROUP BY planta_index ORDER BY planta_index ASC")
            return [int(row[0]) for row in cur.fetchall()]
    except Exception:
        return []


def config_plano(planta_index):
    """(ruta_imagen, escala_px_metro, ancla_x, ancla_y, muros_vectoriales, puntos_infraestructura)
    de la planta, o None. Para cargar/pintar el plano en el visor."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT ruta_imagen, escala_px_metro, ancla_x, ancla_y, muros_vectoriales, "
                "puntos_infraestructura FROM configuracion_mapa WHERE planta_index=%s "
                "ORDER BY id DESC LIMIT 1", (planta_index,))
            return cur.fetchone()
    except Exception:
        return None


def buscar_destino_gps(termino):
    """Resuelve un destino de navegación: 1º infraestructura fija (ubicaciones por código o pasillo),
    y si no, un artículo con coordenadas. Devuelve (etiqueta, mapa_x, mapa_y) o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT CONCAT('UBICACIÓN: ', pasillo, '-', estanteria), mapa_x, mapa_y "
                "FROM ubicaciones WHERE (codigo_articulo=%s OR pasillo=%s) "
                "AND mapa_x IS NOT NULL AND mapa_x != 0 LIMIT 1", (termino, termino))
            res = cur.fetchone()
            if not res:
                cur.execute(
                    "SELECT nombre, mapa_x, mapa_y FROM articulos "
                    "WHERE (nombre LIKE %s OR codigo=%s) AND mapa_x IS NOT NULL AND mapa_x != 0 LIMIT 1",
                    (f"%{termino}%", termino))
                res = cur.fetchone()
            return res
    except Exception:
        return None


def marcar_verificado(codigo) -> int:
    """Marca verificado=1 la ubicación del artículo si estaba a 0. Devuelve filas afectadas."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ubicaciones SET verificado=1 WHERE codigo_articulo=%s AND verificado=0",
                        (codigo,))
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.error("marcar_verificado(%s): %s", codigo, e)
        return 0


def actualizar_coords_epc(epc, x_px, y_px, m_x, m_y) -> bool:
    """Actualiza las coordenadas (px y metros) de una ubicación identificada por EPC."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE ubicaciones SET mapa_x=%s, mapa_y=%s, x_metros=%s, y_metros=%s, "
                "fecha_actualizacion=NOW() WHERE epc=%s", (x_px, y_px, m_x, m_y, epc))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_coords_epc(%s): %s", epc, e)
        return False


def articulos_para_pdf_ubicaciones() -> list:
    """[(codigo, nombre, pasillo, estanteria, nivel)] de artículos con ubicación, en orden de caminata."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, pasillo, estanteria, nivel FROM articulos "
                "WHERE pasillo IS NOT NULL AND pasillo != '' "
                "ORDER BY pasillo ASC, CAST(estanteria AS UNSIGNED) ASC, CAST(nivel AS UNSIGNED) ASC")
            return list(cur.fetchall())
    except Exception:
        return []


def articulos_con_coordenadas() -> list:
    """[(codigo, nombre, mapa_x, mapa_y)] de artículos con coordenada de mapa asignada."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, mapa_x, mapa_y FROM articulos "
                        "WHERE mapa_x IS NOT NULL ORDER BY nombre ASC")
            return list(cur.fetchall())
    except Exception:
        return []


def buscar_articulos_admin(filtro) -> list:
    """[(codigo, nombre, incidencia_ubicacion)] por filtro (nombre/código), incidencias primero."""
    term = f"%{filtro}%"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, incidencia_ubicacion FROM articulos "
                "WHERE nombre LIKE %s OR codigo LIKE %s "
                "ORDER BY incidencia_ubicacion DESC, nombre ASC", (term, term))
            return list(cur.fetchall())
    except Exception:
        return []


def sugerencias_busqueda() -> list:
    """Lista de sugerencias (códigos + nombres de artículos + ubicaciones) para autocompletado."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo FROM articulos WHERE codigo IS NOT NULL AND codigo != '' "
                "UNION SELECT nombre FROM articulos WHERE nombre IS NOT NULL AND nombre != '' "
                "UNION SELECT CONCAT_WS(' ', pasillo, estanteria, balda) FROM ubicaciones "
                "WHERE pasillo IS NOT NULL AND pasillo != ''")
            return [str(row[0]).upper() for row in cur.fetchall() if row and row[0]]
    except Exception:
        return []


def reportar_incidencia_ubicacion(codigo) -> bool:
    """Marca incidencia de ubicación (incidencia_ubicacion=1, ultima_actualizacion) del artículo."""
    emp = _emp()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE articulos SET incidencia_ubicacion=1, ultima_actualizacion=NOW() "
                "WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)", (codigo, emp, emp))
            conn.commit()
        return True
    except Exception as e:
        logger.error("reportar_incidencia_ubicacion(%s): %s", codigo, e)
        return False


def reportar_discrepancia(codigo) -> bool:
    """Registra una discrepancia de stock/ubicación (incidencia_ubicacion=1, ultima_incidencia)."""
    emp = _emp()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE articulos SET incidencia_ubicacion=1, ultima_incidencia=NOW() "
                "WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)", (codigo, emp, emp))
            conn.commit()
        return True
    except Exception as e:
        logger.error("reportar_discrepancia(%s): %s", codigo, e)
        return False
