"""Mensajería empresa↔proveedor del portal (por pedido o general).

`portal_mensajes` (migr 0198). Canal único bidireccional: `autor` ∈ {'empresa','proveedor'}. Un mensaje
del proveedor notifica a la empresa (reutiliza `notificaciones`). Se puede vincular a un pedido concreto
(seguimiento) o dejar general.
"""

from ._common import _audit, _conn, _emp, _filas, _notificar, logger

AUTORES = ("empresa", "proveedor")


def enviar_mensaje(id_proveedor, cuerpo, *, id_pedido=None, autor="empresa", id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    cuerpo = (str(cuerpo or "").strip())[:2000]
    if not cuerpo:
        return None
    aut = autor if autor in AUTORES else "empresa"
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO portal_mensajes (id_empresa, id_proveedor, id_pedido, autor, cuerpo) "
                        "VALUES (%s,%s,%s,%s,%s)", (emp, id_proveedor, id_pedido, aut, cuerpo))
            mid = cur.lastrowid
            c.commit()
        if aut == "proveedor":   # aviso a la empresa de que el proveedor ha escrito
            _notificar("portal_mensaje", "Nuevo mensaje de un proveedor",
                       f"El proveedor {id_proveedor} te ha enviado un mensaje en el portal.", id_empresa=emp)
        _audit("PORTAL_MENSAJE", f"prov={id_proveedor} autor={aut}", "portal_mensajes")
        return mid
    except Exception as e:
        logger.error("enviar_mensaje: %s", e)
        return None


def hilo(id_proveedor, *, id_pedido=None, id_empresa=None, limite=200) -> list:
    """Conversación con un proveedor (opcionalmente de un pedido), en orden cronológico."""
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "id_proveedor=%s"], [emp, id_proveedor]
    if id_pedido is not None:
        cond.append("id_pedido=%s"); params.append(id_pedido)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_pedido, autor, cuerpo, leido, creado_en FROM portal_mensajes "
                        "WHERE " + " AND ".join(cond) + " ORDER BY id ASC LIMIT %s",
                        (*params, int(limite)))
            return _filas(cur)
    except Exception as e:
        logger.error("hilo: %s", e)
        return []


def marcar_leido(id_proveedor, *, id_pedido=None, autor="proveedor", id_empresa=None) -> int:
    """Marca como leídos los mensajes del `autor` indicado (por defecto, los del proveedor)."""
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "id_proveedor=%s", "autor=%s", "leido=0"], [emp, id_proveedor, autor]
    if id_pedido is not None:
        cond.append("id_pedido=%s"); params.append(id_pedido)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE portal_mensajes SET leido=1 WHERE " + " AND ".join(cond), tuple(params))
            n = cur.rowcount
            c.commit()
        return n
    except Exception as e:
        logger.error("marcar_leido: %s", e)
        return 0


def no_leidos(id_empresa=None, autor="proveedor") -> int:
    """Nº de mensajes sin leer del `autor` indicado (para el badge de la GUI)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM portal_mensajes "
                        "WHERE id_empresa=%s AND autor=%s AND leido=0", (emp, autor))
            r = _filas(cur)
            return int(r[0]["n"]) if r else 0
    except Exception as e:
        logger.error("no_leidos: %s", e)
        return 0
