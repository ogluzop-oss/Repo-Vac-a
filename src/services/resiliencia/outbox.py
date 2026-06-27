"""
B7-C — Outbox / Inbox pattern (servidor). Reutiliza la arquitectura de fiscal_cola/contab_cola:
cola idempotente (idempotency_key UNIQUE) con estados + reintentos + backoff + hash. Todo cambio
que deba propagarse (offline->central o central->edge) pasa por aqui. Auditado, multiempresa/tienda.
"""

import datetime as _dt
import hashlib
import json
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.outbox")
ESTADOS = ("pendiente", "enviado", "confirmado", "conflicto", "fallido", "cancelado")
MAX_INTENTOS = 5


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def encolar(entidad, payload, *, operacion="upsert", idempotency_key=None, id_empresa=None,
            id_tienda=0) -> dict:
    """Encola un cambio en el outbox. Idempotente por idempotency_key."""
    eid = _emp(id_empresa)
    h = _hash(payload)
    idem = idempotency_key or f"{entidad}:{id_tienda}:{h[:24]}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO sync_outbox (id_empresa, id_tienda, entidad, operacion, payload, hash, "
                        "idempotency_key, proximo_intento) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW()) "
                        "ON DUPLICATE KEY UPDATE id=id",
                        (eid, id_tienda, entidad, operacion, json.dumps(payload, default=str), h, idem))
            dup = cur.rowcount == 0
            conn.commit()
        return {"ok": True, "idempotency_key": idem, "duplicado": dup}
    except Exception as e:
        logger.error("encolar: %s", e)
        return {"ok": False, "error": str(e)}


def pendientes(*, id_empresa=None, limite=200) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM sync_outbox WHERE id_empresa=%s AND estado IN ('pendiente','fallido') "
                        "AND (proximo_intento IS NULL OR proximo_intento<=NOW()) AND intentos<%s "
                        "ORDER BY id LIMIT %s", (eid, MAX_INTENTOS, int(limite)))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("pendientes: %s", e)
        return []


def marcar(id_outbox, estado, *, error=None, id_empresa=None) -> bool:
    if estado not in ESTADOS:
        raise ValueError(f"estado invalido: {estado}")
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if estado == "confirmado":
                cur.execute("UPDATE sync_outbox SET estado='confirmado', confirmado_en=NOW() WHERE id=%s", (id_outbox,))
            elif estado == "fallido":
                # backoff exponencial: proximo_intento = NOW + 2^intentos minutos
                cur.execute("SELECT intentos FROM sync_outbox WHERE id=%s", (id_outbox,))
                r = cur.fetchone()
                n = ((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) + 1
                espera = min(2 ** n, 60)
                cur.execute("UPDATE sync_outbox SET estado=%s, intentos=%s, error=%s, "
                            "proximo_intento=(NOW() + INTERVAL %s MINUTE) WHERE id=%s",
                            ("fallido" if n < MAX_INTENTOS else "fallido", n, (error or "")[:255], espera, id_outbox))
                cur.execute("INSERT INTO sync_reintentos (id_empresa, id_outbox, intento, resultado, detalle) "
                            "VALUES (%s,%s,%s,'fallido',%s)", (eid, id_outbox, n, (error or "")[:255]))
            else:
                cur.execute("UPDATE sync_outbox SET estado=%s, error=%s WHERE id=%s",
                            (estado, (error or "")[:255] if error else None, id_outbox))
            conn.commit()
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("marcar: %s", e)
        return False


def registrar_inbox(entidad, idempotency_key, payload, *, id_empresa=None, id_tienda=0) -> dict:
    """Recibe un cambio entrante (idempotente). Si ya existe -> duplicado (no reprocesa)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO sync_inbox (id_empresa, id_tienda, entidad, idempotency_key, payload, hash) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
                        (eid, id_tienda, entidad, idempotency_key, json.dumps(payload, default=str), _hash(payload)))
            dup = cur.rowcount == 0
            conn.commit()
        return {"ok": True, "duplicado": dup}
    except Exception as e:
        logger.error("registrar_inbox: %s", e)
        return {"ok": False, "error": str(e)}


def registrar_conflicto(entidad, *, idempotency_key=None, detalle=None, payload_local=None,
                        payload_central=None, id_empresa=None, id_tienda=0) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO sync_conflictos (id_empresa, id_tienda, entidad, idempotency_key, detalle, "
                        "payload_local, payload_central) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_tienda, entidad, idempotency_key, (detalle or "")[:255],
                         json.dumps(payload_local, default=str) if payload_local else None,
                         json.dumps(payload_central, default=str) if payload_central else None))
            cid = cur.lastrowid
            conn.commit()
        log_auditoria("resiliencia", "SYNC_CONFLICTO", "sync_conflictos", f"{entidad} {idempotency_key}")
        return cid
    except Exception as e:
        logger.error("registrar_conflicto: %s", e)
        return None


def resolver_conflicto(id_conflicto, resolucion, *, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sync_conflictos SET estado='resuelto', resolucion=%s, resuelto_en=NOW() WHERE id=%s",
                        (resolucion, id_conflicto))
            conn.commit()
        log_auditoria("resiliencia", "SYNC_CONFLICTO_RESUELTO", "sync_conflictos", f"id={id_conflicto} {resolucion}")
        return True
    except Exception as e:
        logger.error("resolver_conflicto: %s", e)
        return False


def metricas(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) FROM sync_outbox WHERE id_empresa=%s GROUP BY estado", (eid,))
            por_estado = {(r[0] if not isinstance(r, dict) else list(r.values())[0]):
                          (r[1] if not isinstance(r, dict) else list(r.values())[1]) for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM sync_conflictos WHERE id_empresa=%s AND estado='abierto'", (eid,))
            r = cur.fetchone()
            conflictos = (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0
        return {"outbox": por_estado, "pendientes": por_estado.get("pendiente", 0) + por_estado.get("fallido", 0),
                "conflictos_abiertos": conflictos}
    except Exception as e:
        logger.error("metricas outbox: %s", e)
        return {"outbox": {}, "pendientes": 0, "conflictos_abiertos": 0}
