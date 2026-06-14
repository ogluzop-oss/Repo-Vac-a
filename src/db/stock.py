"""
Aislamiento de STOCK por tienda (Fase 3b.1 — 2c).

Modelo: `articulos.Stock_tienda` es el stock de trabajo de la tienda ACTIVA
(todo el código existente lo sigue usando sin cambios); `stock_tienda` guarda el
stock PERSISTENTE de cada tienda. Al cambiar de tienda se vuelca el stock de la
tienda saliente a `stock_tienda` y se carga el de la entrante en
`articulos.Stock_tienda`. Resultado: aislamiento real por tienda sin reescribir
los ~40 puntos que leen/escriben `articulos.Stock_tienda`.

Ver [[project_multitenant]] / [[project_centro_documental]].
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("stock_db")


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def tienda_por_defecto(id_empresa=None):
    """Tienda por defecto (menor id) de la empresa: la que respalda el stock cuando
    no hay tienda activa fijada."""
    id_empresa = id_empresa or _empresa()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT MIN(id) FROM tiendas WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            v = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            return v
    except Exception:
        return None


def _tienda_efectiva(id_tienda):
    if id_tienda is not None:
        return id_tienda
    try:
        from src.db.empresa import tienda_actual_id
        t = tienda_actual_id()
        if t is not None:
            return t
    except Exception:
        pass
    return tienda_por_defecto()


def flush_stock(id_tienda=None, id_empresa=None) -> bool:
    """Vuelca el stock de trabajo (articulos.Stock_tienda) a stock_tienda para la
    tienda indicada (la activa/por defecto si None). Persiste lo que se ha vendido/
    recibido durante la sesión bajo esa tienda."""
    id_empresa = id_empresa or _empresa()
    tid = _tienda_efectiva(id_tienda)
    if tid is None:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO stock_tienda (id_empresa, id_tienda, codigo_articulo, stock) "
                "SELECT id_empresa, %s, codigo, COALESCE(Stock_tienda,0) FROM articulos "
                "WHERE id_empresa=%s AND codigo IS NOT NULL AND codigo<>'' "
                "ON DUPLICATE KEY UPDATE stock=VALUES(stock)",
                (tid, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("flush_stock(%s): %s", tid, e)
        return False


def cargar_stock(id_tienda=None, id_empresa=None) -> bool:
    """Carga en articulos.Stock_tienda el stock persistente de la tienda indicada
    (0 para los artículos sin existencias en esa tienda)."""
    id_empresa = id_empresa or _empresa()
    tid = _tienda_efectiva(id_tienda)
    if tid is None:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE articulos a "
                "LEFT JOIN stock_tienda st "
                "  ON st.codigo_articulo=a.codigo AND st.id_tienda=%s "
                "SET a.Stock_tienda = COALESCE(st.stock, 0) "
                "WHERE a.id_empresa=%s",
                (tid, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cargar_stock(%s): %s", tid, e)
        return False


def cambiar_stock_de_tienda(id_tienda_origen, id_tienda_destino, id_empresa=None):
    """Persiste el stock de la tienda saliente y carga el de la entrante.
    Llamado por el cambio de contexto de tienda."""
    id_empresa = id_empresa or _empresa()
    # 1) Guardar lo trabajado bajo la tienda saliente (o la por defecto).
    flush_stock(id_tienda_origen, id_empresa)
    # 2) Cargar el stock de la tienda entrante en el stock de trabajo.
    cargar_stock(id_tienda_destino, id_empresa)
