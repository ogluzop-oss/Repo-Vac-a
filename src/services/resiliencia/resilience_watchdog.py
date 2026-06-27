"""
B7-G — Autoheal / Watchdog. Detecta servicios caidos, colas bloqueadas, sync detenidas, errores
repetidos y reintentos agotados; ejecuta acciones (reencolar/reanudar/notificar/auditar). Reutiliza
observabilidad.health, outbox, circuit_breaker, incidentes. Pensado para el Scheduler.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.watchdog")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _val(cur):
    r = cur.fetchone()
    return ((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0


def diagnosticar(*, id_empresa=None) -> dict:
    """Diagnostico de salud operativa (subsistemas + colas + breakers + sync)."""
    eid = _emp(id_empresa)
    diag = {"subsistemas": {}, "outbox_pendiente": 0, "outbox_agotado": 0, "breakers_abiertos": 0,
            "conflictos": 0}
    try:
        from src.services.observabilidad import health
        diag["subsistemas"] = health.health().get("subsistemas", {})
    except Exception:
        pass
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM sync_outbox WHERE id_empresa=%s AND estado IN ('pendiente','fallido')",
                        (eid,))
            diag["outbox_pendiente"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM sync_outbox WHERE id_empresa=%s AND estado='fallido' AND intentos>=5",
                        (eid,))
            diag["outbox_agotado"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM sync_conflictos WHERE id_empresa=%s AND estado='abierto'", (eid,))
            diag["conflictos"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM circuit_breakers WHERE estado='open'")
            diag["breakers_abiertos"] = int(_val(cur))
    except Exception as e:
        logger.error("diagnosticar: %s", e)
    return diag


def ejecutar(*, id_empresa=None, aplicar=True) -> dict:
    """Ejecuta el watchdog: detecta problemas y aplica acciones de autoheal. Auditado."""
    eid = _emp(id_empresa)
    diag = diagnosticar(id_empresa=eid)
    acciones = []

    # 1) Subsistemas caidos -> alerta + incidente
    caidos = [k for k, v in diag["subsistemas"].items() if v is False]
    if caidos:
        acciones.append(f"alerta_subsistemas:{','.join(caidos)}")
        if aplicar:
            _alertar(f"Subsistemas caidos: {', '.join(caidos)}", eid)

    # 2) Outbox con backlog -> reanudar sync
    if diag["outbox_pendiente"] > 0 and aplicar:
        try:
            from src.services.resiliencia import sync_engine
            r = sync_engine.push_offline_a_central(id_empresa=eid)
            acciones.append(f"sync_reanudada:{r['resumen']}")
        except Exception as e:
            logger.debug("reanudar sync: %s", e)

    # 3) Reintentos agotados -> reencolar (resetea proximo_intento e intentos)
    if diag["outbox_agotado"] > 0 and aplicar:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE sync_outbox SET estado='pendiente', intentos=0, proximo_intento=NOW() "
                            "WHERE id_empresa=%s AND estado='fallido' AND intentos>=5", (eid,))
                conn.commit()
            acciones.append(f"reencolados:{diag['outbox_agotado']}")
        except Exception as e:
            logger.debug("reencolar: %s", e)

    # 4) Breakers abiertos -> notificar (no auto-resetea; lo hace el cooldown)
    if diag["breakers_abiertos"] > 0:
        acciones.append(f"breakers_abiertos:{diag['breakers_abiertos']}")

    # 5) Conflictos abiertos -> notificar para resolucion manual
    if diag["conflictos"] > 0 and aplicar:
        _alertar(f"{diag['conflictos']} conflictos de sincronizacion pendientes", eid)
        acciones.append(f"conflictos:{diag['conflictos']}")

    log_auditoria("resiliencia", "WATCHDOG", "sync_outbox", f"acciones={acciones}")
    return {"ok": True, "diagnostico": diag, "acciones": acciones}


def _alertar(mensaje, eid):
    try:
        from src.services.observabilidad import alertas_tecnicas
        alertas_tecnicas.emitir("watchdog", mensaje, severidad="alta", id_empresa=eid)
    except Exception:
        pass


def _job_watchdog(id_empresa):
    return f"watchdog={ejecutar(id_empresa=id_empresa).get('acciones')}"


def registrar_jobs_watchdog(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("resiliencia_watchdog", _job_watchdog)
    scheduler.registrar_job("resiliencia_watchdog", intervalo_horas=1, descripcion="Watchdog de resiliencia",
                            id_empresa=id_empresa)
