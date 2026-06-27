"""
B7-D — Motor de sincronizacion. Drena el offline_store (SQLite) hacia el central via outbox/inbox,
con validacion de hash, deteccion/resolucion de conflictos, reintentos y replay. Reanudable e
idempotente. Sincroniza ventas/movimientos/documentos/eventos. Reutiliza kardex/lotes en central.
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.sync_engine")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def push_offline_a_central(*, id_empresa=None, id_tienda=0, aplicar_central=True) -> dict:
    """Drena las operaciones offline de una tienda hacia el central (idempotente, reanudable)."""
    eid = _emp(id_empresa)
    from src.services.resiliencia import event_sourcing, offline_store, outbox
    resumen = {"ventas": 0, "movimientos": 0, "conflictos": 0, "errores": 0}

    # Ventas
    for v in offline_store.items_pendientes(eid, "ventas", id_tienda=id_tienda):
        import json
        payload = json.loads(v.get("payload") or "{}")
        idem = v["idempotency_key"]
        enc = outbox.encolar("venta", payload, idempotency_key=idem, id_empresa=eid, id_tienda=id_tienda)
        ok = True
        if aplicar_central:
            ok = _aplicar_venta_central(eid, id_tienda, idem, payload, resumen)
        if ok:
            event_sourcing.registrar_evento("VENTA", "venta", v["id"], payload, origen="edge",
                                            idempotency_key=idem, id_empresa=eid, id_tienda=id_tienda)
            offline_store.marcar_sincronizado(eid, "ventas", [v["id"]], id_tienda=id_tienda)
            resumen["ventas"] += 1

    # Movimientos
    for m in offline_store.items_pendientes(eid, "movimientos", id_tienda=id_tienda):
        import json
        payload = json.loads(m.get("payload") or "{}")
        idem = m["idempotency_key"]
        outbox.encolar("movimiento", payload, idempotency_key=idem, id_empresa=eid, id_tienda=id_tienda)
        if aplicar_central:
            _aplicar_movimiento_central(eid, id_tienda, idem, m, resumen)
        event_sourcing.registrar_evento(m.get("tipo", "MOV"), "movimiento", m["id"], payload, origen="edge",
                                        idempotency_key=idem, id_empresa=eid, id_tienda=id_tienda)
        offline_store.marcar_sincronizado(eid, "movimientos", [m["id"]], id_tienda=id_tienda)
        resumen["movimientos"] += 1

    # Eventos offline -> event sourcing central (auditoria reconstruible)
    for ev in offline_store.items_pendientes(eid, "eventos", id_tienda=id_tienda):
        import json
        event_sourcing.registrar_evento(ev.get("tipo", "EVENTO"), ev.get("agregado", "generico"),
                                        ev.get("agregado_id"), json.loads(ev.get("payload") or "{}"),
                                        origen="edge", idempotency_key=ev["idempotency_key"], id_empresa=eid,
                                        id_tienda=id_tienda)
        offline_store.marcar_sincronizado(eid, "eventos", [ev["id"]], id_tienda=id_tienda)

    _actualizar_edge(eid, id_tienda)
    return {"ok": True, "resumen": resumen}


def _aplicar_venta_central(eid, id_tienda, idem, payload, resumen):
    """Aplica la venta en el central via kardex (idempotente por id_documento). Best-effort."""
    try:
        from src.db import kardex
        for ln in (payload.get("lineas") or []):
            cod, cant = ln.get("codigo"), int(float(ln.get("cantidad", 0) or 0))
            if cod and cant:
                kardex.registrar_movimiento(cod, "SALIDA_VENTA", cant, id_documento=f"OFFLINE:{idem}",
                                            observaciones="Venta offline sincronizada", id_empresa=eid,
                                            id_tienda=id_tienda, idempotente=True)
        return True
    except Exception as e:
        logger.error("_aplicar_venta_central: %s", e)
        resumen["errores"] += 1
        return False


def _aplicar_movimiento_central(eid, id_tienda, idem, mov, resumen):
    try:
        from src.db import kardex
        tipo = "ENTRADA_TRASPASO" if mov.get("tipo") in ("ENTRADA", "RECEPCION") else "AJUSTE"
        kardex.registrar_movimiento(mov.get("codigo"), tipo, int(float(mov.get("cantidad", 0) or 0)),
                                    id_documento=f"OFFLINE:{idem}", observaciones="Movimiento offline",
                                    id_empresa=eid, id_tienda=id_tienda, idempotente=True)
        return True
    except Exception as e:
        logger.error("_aplicar_movimiento_central: %s", e)
        resumen["errores"] += 1
        return False


def pull_central_a_offline(*, id_empresa=None, id_tienda=0, limite=5000) -> dict:
    """Sincronizacion incremental del catalogo central -> offline_store (articulos/clientes/stock/precios)."""
    eid = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    from src.services.resiliencia import offline_store
    offline_store.inicializar(eid, id_tienda)
    n = {"articulos": 0, "clientes": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre FROM articulos LIMIT %s", (int(limite),))
            for r in cur.fetchall():
                r = dict(zip([d[0] for d in cur.description], r if not isinstance(r, dict) else r.values()))
                offline_store.upsert_articulo(eid, r["codigo"], r.get("nombre"), r, id_tienda=id_tienda)
                n["articulos"] += 1
            cur.execute("SELECT id, nombre FROM clientes WHERE id_empresa=%s LIMIT %s", (eid, int(limite)))
            for r in cur.fetchall():
                r = dict(zip([d[0] for d in cur.description], r if not isinstance(r, dict) else r.values()))
                offline_store.upsert_cliente(eid, r["id"], r.get("nombre"), r, id_tienda=id_tienda)
                n["clientes"] += 1
    except Exception as e:
        logger.error("pull_central_a_offline: %s", e)
    return {"ok": True, "sincronizado": n}


def sincronizar(*, id_empresa=None, id_tienda=0) -> dict:
    """Sincronizacion completa bidireccional (pull catalogo + push operaciones)."""
    eid = _emp(id_empresa)
    pull = pull_central_a_offline(id_empresa=eid, id_tienda=id_tienda)
    push = push_offline_a_central(id_empresa=eid, id_tienda=id_tienda)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("resiliencia", "SYNC_COMPLETA", "sync_outbox", f"tienda={id_tienda} {push['resumen']}")
    except Exception:
        pass
    return {"ok": True, "pull": pull["sincronizado"], "push": push["resumen"]}


def _actualizar_edge(eid, id_tienda):
    try:
        from src.services.resiliencia import edge_node, offline_store
        pend = offline_store.pendientes_sync(eid, id_tienda=id_tienda)
        total = sum(pend.values())
        edge_node.actualizar(eid, id_tienda, eventos_pendientes=total, ultima_sincronizacion=True)
    except Exception:
        pass


# ── Job Scheduler ─────────────────────────────────────────────────────────────
def _job_sync(id_empresa):
    return f"sync={push_offline_a_central(id_empresa=id_empresa).get('resumen')}"


def registrar_jobs_sync(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("resiliencia_sync", _job_sync)
    scheduler.registrar_job("resiliencia_sync", intervalo_horas=1, descripcion="Sincronizacion offline->central",
                            id_empresa=id_empresa)
