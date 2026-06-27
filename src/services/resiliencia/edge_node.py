"""
B7-H — Store Edge Node. Modela el estado de una tienda (online/degradado/offline/recuperacion) y
orquesta su operacion local (offline_store + cache) con sincronizacion posterior. Reutiliza
offline_store/sync_engine. Multiempresa/tienda.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.edge_node")
MODOS = ("online", "degradado", "offline", "recuperacion")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def registrar(id_empresa, id_tienda, *, nombre=None) -> dict:
    """Registra/inicializa el edge node de una tienda (idempotente) + su offline_store."""
    eid = _emp(id_empresa)
    from src.services.resiliencia import offline_store
    offline_store.inicializar(eid, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO edge_nodes (id_empresa, id_tienda, nombre) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=COALESCE(VALUES(nombre), nombre)",
                        (eid, id_tienda, nombre))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("registrar edge: %s", e)
        return {"ok": False, "error": str(e)}


def set_modo(id_empresa, id_tienda, modo) -> bool:
    if modo not in MODOS:
        raise ValueError(f"modo invalido: {modo}")
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO edge_nodes (id_empresa, id_tienda, modo) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE modo=VALUES(modo), actualizado=NOW()", (eid, id_tienda, modo))
            conn.commit()
        log_auditoria("resiliencia", "EDGE_MODO", "edge_nodes", f"tienda={id_tienda} {modo}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("set_modo: %s", e)
        return False


def actualizar(id_empresa, id_tienda, *, eventos_pendientes=None, salud=None, ultima_sincronizacion=False) -> bool:
    eid = _emp(id_empresa)
    sets, params = [], []
    if eventos_pendientes is not None:
        sets.append("eventos_pendientes=%s"); params.append(int(eventos_pendientes))
    if salud is not None:
        sets.append("salud=%s"); params.append(salud)
    if ultima_sincronizacion:
        sets.append("ultima_sincronizacion=NOW()")
    if not sets:
        return False
    params.extend([eid, id_tienda])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE edge_nodes SET {', '.join(sets)}, actualizado=NOW() "
                        f"WHERE id_empresa=%s AND id_tienda=%s", params)
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar edge: %s", e)
        return False


def estado(id_empresa, id_tienda) -> dict:
    eid = _emp(id_empresa)
    from src.services.resiliencia import offline_store
    nodo = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM edge_nodes WHERE id_empresa=%s AND id_tienda=%s", (eid, id_tienda))
            r = cur.fetchone()
            nodo = _fila(cur, r) if r else {"modo": "online"}
    except Exception:
        nodo = {"modo": "online"}
    try:
        nodo["offline"] = offline_store.estadisticas(eid, id_tienda=id_tienda)
        nodo["pendientes"] = offline_store.pendientes_sync(eid, id_tienda=id_tienda)
    except Exception:
        pass
    return nodo


def listar(*, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM edge_nodes WHERE id_empresa=%s ORDER BY id_tienda", (eid,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar edge: %s", e)
        return []


def entrar_offline(id_empresa, id_tienda) -> dict:
    """La tienda pierde conexion: pasa a modo offline y precarga catalogo local si puede."""
    eid = _emp(id_empresa)
    set_modo(eid, id_tienda, "offline")
    return {"ok": True, "modo": "offline"}


def reconectar(id_empresa, id_tienda) -> dict:
    """Vuelve la conexion: modo recuperacion -> sincroniza -> online."""
    eid = _emp(id_empresa)
    set_modo(eid, id_tienda, "recuperacion")
    from src.services.resiliencia import sync_engine
    r = sync_engine.sincronizar(id_empresa=eid, id_tienda=id_tienda)
    set_modo(eid, id_tienda, "online")
    return {"ok": True, "modo": "online", "sincronizacion": r}
