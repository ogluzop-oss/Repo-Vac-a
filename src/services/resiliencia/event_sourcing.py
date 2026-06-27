"""
B7-E — Event sourcing operativo (servidor). NO crea sistema paralelo: complementa kardex/auditoria/
hash-chain con un log de eventos operativos encadenado (operational_events) + snapshots + replay.
Permite reconstruir el estado de un agregado (p.ej. stock de un articulo) y auditar/repetir. Multiempresa.
"""

import hashlib
import json
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.event_sourcing")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def registrar_evento(tipo, agregado, agregado_id, payload, *, origen="central",
                     idempotency_key=None, id_empresa=None, id_tienda=0) -> dict:
    """Anade un evento inmutable encadenado por hash. Idempotente por idempotency_key."""
    eid = _emp(id_empresa)
    idem = idempotency_key or f"{agregado}:{agregado_id}:{tipo}:{hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT hash, secuencia FROM operational_events WHERE id_empresa=%s ORDER BY secuencia DESC "
                        "LIMIT 1", (eid,))
            r = cur.fetchone()
            prev = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            seq = ((r[1] if not isinstance(r, dict) else list(r.values())[1]) if r else 0) + 1
            h = hashlib.sha256(f"{prev}|{tipo}|{idem}|{json.dumps(payload, sort_keys=True, default=str)}".encode()).hexdigest()
            cur.execute("INSERT INTO operational_events (id_empresa, id_tienda, tipo, agregado, agregado_id, payload, "
                        "hash, hash_anterior, secuencia, origen, idempotency_key) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
                        (eid, id_tienda, tipo, agregado, str(agregado_id), json.dumps(payload, default=str),
                         h, prev, seq, origen, idem))
            dup = cur.rowcount == 0
            conn.commit()
        return {"ok": True, "hash": h, "secuencia": seq, "duplicado": dup}
    except Exception as e:
        logger.error("registrar_evento: %s", e)
        return {"ok": False, "error": str(e)}


def eventos(agregado, agregado_id, *, desde_secuencia=0, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM operational_events WHERE id_empresa=%s AND agregado=%s AND agregado_id=%s "
                        "AND secuencia>%s ORDER BY secuencia", (eid, agregado, str(agregado_id), desde_secuencia))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("eventos: %s", e)
        return []


def replay(agregado, agregado_id, *, reductor=None, id_empresa=None) -> dict:
    """Reconstruye el estado aplicando los eventos en orden. reductor(estado, evento)->estado.
    Por defecto reduce stock para agregado 'articulo' (ENTRADA suma / SALIDA resta)."""
    eid = _emp(id_empresa)
    # Parte del ultimo snapshot si existe.
    estado, base_seq = _ultimo_snapshot(agregado, agregado_id, eid)
    evs = eventos(agregado, agregado_id, desde_secuencia=base_seq, id_empresa=eid)
    red = reductor or _reductor_stock
    for ev in evs:
        try:
            ev_payload = json.loads(ev.get("payload") or "{}")
        except Exception:
            ev_payload = {}
        estado = red(estado, {"tipo": ev["tipo"], "payload": ev_payload})
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO event_replay_log (id_empresa, agregado, agregado_id, eventos, "
                        "desde_secuencia, hasta_secuencia) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eid, agregado, str(agregado_id), len(evs), base_seq,
                         evs[-1]["secuencia"] if evs else base_seq))
            conn.commit()
    except Exception:
        pass
    log_auditoria("resiliencia", "EVENT_REPLAY", "operational_events", f"{agregado}:{agregado_id} n={len(evs)}")
    return {"estado": estado, "eventos_aplicados": len(evs), "desde_snapshot": base_seq}


def _reductor_stock(estado, ev):
    estado = estado or {"cantidad": 0.0}
    p = ev.get("payload") or {}
    cant = float(p.get("cantidad", 0) or 0)
    if ev["tipo"] in ("ENTRADA", "RECEPCION", "ENTRADA_PRODUCCION", "DEVOLUCION"):
        estado["cantidad"] = estado.get("cantidad", 0) + cant
    elif ev["tipo"] in ("SALIDA", "VENTA", "VENTA_OFFLINE", "MOV_OFFLINE", "SALIDA_PRODUCCION"):
        estado["cantidad"] = estado.get("cantidad", 0) - cant
    return estado


def _ultimo_snapshot(agregado, agregado_id, eid):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado, secuencia FROM event_snapshots WHERE id_empresa=%s AND agregado=%s "
                        "AND agregado_id=%s ORDER BY secuencia DESC LIMIT 1", (eid, agregado, str(agregado_id)))
            r = cur.fetchone()
            if r:
                r = list(r.values()) if isinstance(r, dict) else r
                return json.loads(r[0] or "{}"), int(r[1] or 0)
    except Exception:
        pass
    return None, 0


def crear_snapshot(agregado, agregado_id, *, id_empresa=None) -> dict:
    """Materializa un checkpoint del estado reconstruido para acelerar futuros replays."""
    eid = _emp(id_empresa)
    rep = replay(agregado, agregado_id, id_empresa=eid)
    estado = rep["estado"]
    evs = eventos(agregado, agregado_id, id_empresa=eid)
    seq = evs[-1]["secuencia"] if evs else 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO event_snapshots (id_empresa, agregado, agregado_id, secuencia, estado) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, agregado, str(agregado_id), seq,
                                                    json.dumps(estado, default=str)))
            conn.commit()
        log_auditoria("resiliencia", "EVENT_SNAPSHOT", "event_snapshots", f"{agregado}:{agregado_id} seq={seq}")
        return {"ok": True, "secuencia": seq, "estado": estado}
    except Exception as e:
        logger.error("crear_snapshot: %s", e)
        return {"ok": False, "error": str(e)}


def verificar_cadena(*, id_empresa=None) -> dict:
    """Verifica la integridad del encadenado hash de operational_events."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT hash, hash_anterior FROM operational_events WHERE id_empresa=%s ORDER BY secuencia",
                        (eid,))
            rows = [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        return {"ok": False, "error": str(e)}
    prev = None
    for r in rows:
        if r["hash_anterior"] != prev:
            return {"ok": False, "roto_en": r["hash"]}
        prev = r["hash"]
    return {"ok": True, "eventos": len(rows)}
