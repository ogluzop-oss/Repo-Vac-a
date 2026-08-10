"""
Familias de producto — vocabulario GESTIONABLE por empresa + vínculo GLOBAL con los artículos.

Cada artículo puede pertenecer a UNA familia (`articulos.id_familia`). La familia es la fuente única del
grupo comercial y se usa para filtrar búsquedas, promociones por familia, analítica, etc. El vínculo vive en
la tabla base `articulos`, así que es global (visible desde cualquier módulo). Renombrar una familia NO rompe
los enlaces (van por id). Multiempresa. Reutiliza la conexión y el contexto de empresa existentes (N7).
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("familias")


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


# ── CRUD de familias ──────────────────────────────────────────────────────────
def crear_familia(nombre, descripcion=None, color=None, restringida=False, id_empresa=None):
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO familias_producto (id_empresa, nombre, descripcion, color, restringida) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, nombre, descripcion, color, 1 if restringida else 0))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_familia: %s", e)
        return None


def listar_familias(id_empresa=None, solo_activas=True):
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM familias_producto WHERE id_empresa=%s"
            if solo_activas:
                q += " AND activo=1"
            q += " ORDER BY orden, nombre"
            cur.execute(q, (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_familias: %s", e)
        return []


def obtener_familia(id_familia, id_empresa=None):
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM familias_producto WHERE id=%s AND id_empresa=%s",
                        (id_familia, id_empresa))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_familia: %s", e)
        return None


def actualizar_familia(id_familia, id_empresa=None, **campos):
    id_empresa = _empresa(id_empresa)
    datos = {k: v for k, v in campos.items()
             if k in ("nombre", "descripcion", "color", "orden", "activo", "restringida")}
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE familias_producto SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_familia, id_empresa))
            return True
    except Exception as e:
        logger.error("actualizar_familia: %s", e)
        return False


def eliminar_familia(id_familia, id_empresa=None):
    """Elimina la familia y DESVINCULA sus artículos (id_familia → NULL). Nunca borra artículos."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET id_familia=NULL WHERE id_familia=%s AND id_empresa=%s",
                        (id_familia, id_empresa))
            cur.execute("DELETE FROM familias_producto WHERE id=%s AND id_empresa=%s",
                        (id_familia, id_empresa))
            return True
    except Exception as e:
        logger.error("eliminar_familia: %s", e)
        return False


# ── Vínculo artículo ↔ familia (global) ───────────────────────────────────────
def asignar_familia(codigo, id_familia, id_empresa=None):
    """Asigna (o desasigna si `id_familia` es None) la familia de un artículo. Vínculo GLOBAL en `articulos`."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET id_familia=%s WHERE codigo=%s AND id_empresa=%s",
                        (id_familia, codigo, id_empresa))
            return True
    except Exception as e:
        logger.error("asignar_familia: %s", e)
        return False


def familia_de_articulo(codigo, id_empresa=None):
    """Familia (dict) del artículo, o None si no tiene."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT f.* FROM articulos a JOIN familias_producto f ON f.id=a.id_familia "
                        "WHERE a.codigo=%s AND a.id_empresa=%s", (codigo, id_empresa))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("familia_de_articulo: %s", e)
        return None


def articulos_de_familia(id_familia, id_empresa=None, limite=2000):
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, precio, emoji FROM articulos "
                        "WHERE id_familia=%s AND id_empresa=%s ORDER BY nombre LIMIT %s",
                        (id_familia, id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("articulos_de_familia: %s", e)
        return []


def contar_por_familia(id_empresa=None):
    """{id_familia: n_articulos} de la empresa (clave None = artículos sin familia)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_familia, COUNT(*) FROM articulos WHERE id_empresa=%s GROUP BY id_familia",
                        (id_empresa,))
            return {r[0]: r[1] for r in cur.fetchall()}
    except Exception as e:
        logger.error("contar_por_familia: %s", e)
        return {}


# ── Fase 2: núcleo reutilizable (filtrado, operaciones masivas, analítica) ────
def articulos_filtrados(query="", id_familia=None, id_empresa=None, limite=200):
    """Listado de artículos filtrado por TEXTO (código/nombre) y opcionalmente por FAMILIA.

    Punto ÚNICO de filtrado por familia para pantallas de lista (Stock, Catálogo, etiquetas…): así todas
    comparten la misma consulta en vez de duplicar el WHERE. `id_familia=None` no filtra por familia;
    `id_familia=0` selecciona los artículos SIN familia. Devuelve
    (codigo, nombre, Stock_tienda, Stock_total, Stock_central).
    """
    id_empresa = _empresa(id_empresa)
    try:
        like = f"%{(query or '').strip()}%"
        cond = ["id_empresa=%s", "(codigo LIKE %s OR nombre LIKE %s)"]
        params = [id_empresa, like, like]
        if id_familia == 0:
            cond.append("id_familia IS NULL")
        elif id_familia is not None:
            cond.append("id_familia=%s")
            params.append(id_familia)
        params.append(int(limite))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                "COALESCE(Stock_central,0) FROM articulos WHERE " + " AND ".join(cond) +
                " ORDER BY nombre ASC LIMIT %s", tuple(params))
            return cur.fetchall()
    except Exception as e:
        logger.error("articulos_filtrados: %s", e)
        return []


def listar_articulos_con_familia(id_empresa=None, limite=2000):
    """Todos los artículos de la empresa con su familia asignada (para gestión de familias en el TPV).
    Devuelve dicts {codigo, nombre, precio, id_familia, familia}. `familia` es None si no tiene."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT a.codigo AS codigo, a.nombre AS nombre, COALESCE(a.precio,0) AS precio, "
                "a.emoji AS emoji, a.id_familia AS id_familia, f.nombre AS familia "
                "FROM articulos a LEFT JOIN familias_producto f "
                "ON f.id=a.id_familia AND f.id_empresa=a.id_empresa "
                "WHERE a.id_empresa=%s ORDER BY a.nombre ASC LIMIT %s", (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_articulos_con_familia: %s", e)
        return []


def cambiar_precio_masivo(id_familia, modo, valor, id_empresa=None):
    """Operación MASIVA sobre los artículos de una familia. Devuelve el nº de artículos afectados.

    modo:
      · 'pct'  → precio = precio * (1 + valor/100)  (subida/bajada porcentual)
      · 'fijo' → precio = valor                       (mismo P.V.P. para toda la familia)
      · 'iva'  → iva    = valor                       (mismo tipo de IVA para toda la familia)
    Reutiliza la tabla base `articulos` (fuente única); NO crea motor de precios paralelo.
    """
    id_empresa = _empresa(id_empresa)
    if id_familia is None:
        return 0
    try:
        valor = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if modo == "pct":
                sql = "UPDATE articulos SET precio=ROUND(COALESCE(precio,0)*(1+%s/100),2)"
            elif modo == "fijo":
                sql = "UPDATE articulos SET precio=%s"
            elif modo == "iva":
                sql = "UPDATE articulos SET iva=%s"
            else:
                return 0
            cur.execute(sql + " WHERE id_familia=%s AND id_empresa=%s", (valor, id_familia, id_empresa))
            return cur.rowcount
    except Exception as e:
        logger.error("cambiar_precio_masivo: %s", e)
        return 0


def ventas_por_familia(id_empresa=None, dias=30):
    """Ventas agregadas por familia en los últimos `dias`. Para BI/analítica.

    Devuelve lista de dicts [{familia, id_familia, unidades, importe}] ordenada por importe desc.
    Los artículos SIN familia se agrupan bajo `familia='(Sin familia)'`. Multiempresa por el JOIN con
    `articulos` (scope de la empresa), reutilizando la tabla plana `ventas` (codigo/cantidad/total).
    """
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id AS id_familia,
                       COALESCE(f.nombre, '(Sin familia)') AS familia,
                       COALESCE(SUM(v.cantidad), 0) AS unidades,
                       COALESCE(SUM(v.total), 0)    AS importe
                FROM ventas v
                JOIN articulos a ON a.codigo = v.codigo AND a.id_empresa = %s
                LEFT JOIN familias_producto f ON f.id = a.id_familia
                WHERE v.fecha >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY f.id, familia
                ORDER BY importe DESC
                """,
                (id_empresa, int(dias)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("ventas_por_familia: %s", e)
        return []
