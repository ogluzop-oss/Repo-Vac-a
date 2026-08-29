"""
Chat por pedido B2B (Smart Suppliers B2B · Fase 3). Mensajes rígidamente ligados a un `id_tx`
(transaccion_comercial), visibles tanto desde el Portal Empresa como desde el Portal Proveedor.

"No leídos" se calcula por marca de agua (`b2b_pedido_lecturas`: último instante en que ESE lado leyó
ESE pedido) en vez de un flag `leido` por mensaje — mismo patrón que `actividad_vistas`
(src/services/actividad/badges.py) para el resto de la app. Sin tiempo real: el chat se recarga por
página completa, coherente con el resto de los portales B2B (sin JS de sondeo en ningún sitio hoy).
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_chat")

LADOS = ("empresa", "proveedor")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _otro_lado(lado):
    return "proveedor" if lado == "empresa" else "empresa"


def enviar_mensaje(id_tx, lado: str, autor_nombre, cuerpo: str) -> dict:
    if lado not in LADOS:
        return {"ok": False, "error": "lado_invalido"}
    cuerpo = (cuerpo or "").strip()
    if not cuerpo:
        return {"ok": False, "error": "mensaje_vacio"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_pedido_mensajes (id_tx, autor_tipo, autor_nombre, cuerpo) "
                "VALUES (%s,%s,%s,%s)", (id_tx, lado, autor_nombre, cuerpo))
            id_mensaje = cur.lastrowid
            conn.commit()
        # Enviar un mensaje también cuenta como "leído" lo propio hasta ahora (evita que el remitente
        # se vea a sí mismo como no-leído tras enviar).
        marcar_leido(id_tx, lado)
        return {"ok": True, "id_mensaje": id_mensaje}
    except Exception as e:
        logger.error("enviar_mensaje(%s,%s): %s", id_tx, lado, e)
        return {"ok": False, "error": "error_interno"}


def listar_mensajes(id_tx) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_pedido_mensajes WHERE id_tx=%s ORDER BY creado_en",
                        (id_tx,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_mensajes(%s): %s", id_tx, e)
        return []


def marcar_leido(id_tx, lado: str) -> None:
    if lado not in LADOS:
        return
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_pedido_lecturas (id_tx, lado, ultima_lectura) VALUES (%s,%s,NOW(6)) "
                "ON DUPLICATE KEY UPDATE ultima_lectura=NOW(6)", (id_tx, lado))
            conn.commit()
    except Exception as e:
        logger.debug("marcar_leido(%s,%s): %s", id_tx, lado, e)


def no_leidos(id_tx, lado: str) -> int:
    """Mensajes del OTRO lado posteriores a la última lectura de `lado` (todos, si nunca se leyó)."""
    if lado not in LADOS:
        return 0
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ultima_lectura FROM b2b_pedido_lecturas WHERE id_tx=%s AND lado=%s",
                        (id_tx, lado))
            row = cur.fetchone()
            marca = _fila(cur, row)["ultima_lectura"] if row else None
            if marca:
                cur.execute(
                    "SELECT COUNT(*) FROM b2b_pedido_mensajes WHERE id_tx=%s AND autor_tipo=%s "
                    "AND creado_en > %s", (id_tx, _otro_lado(lado), marca))
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM b2b_pedido_mensajes WHERE id_tx=%s AND autor_tipo=%s",
                    (id_tx, _otro_lado(lado)))
            r = cur.fetchone()
            return int(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception as e:
        logger.error("no_leidos(%s,%s): %s", id_tx, lado, e)
        return 0


def no_leidos_totales_empresa(id_empresa) -> int:
    """Suma de no-leídos de TODOS los pedidos B2B de la empresa (para el badge de navegación)."""
    return _no_leidos_totales("id_empresa", id_empresa, "empresa")


def no_leidos_totales_proveedor(id_suministrador) -> int:
    return _no_leidos_totales("id_suministrador", id_suministrador, "proveedor")


def _no_leidos_totales(columna_filtro, valor, lado) -> int:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT id_tx FROM transaccion_comercial WHERE {columna_filtro}=%s "
                       "AND origen='b2b'", (valor,))
            ids_tx = [r[0] if not isinstance(r, dict) else list(r.values())[0]
                     for r in cur.fetchall()]
        return sum(no_leidos(id_tx, lado) for id_tx in ids_tx)
    except Exception as e:
        logger.error("_no_leidos_totales(%s,%s): %s", columna_filtro, valor, e)
        return 0
