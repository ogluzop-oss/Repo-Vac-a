"""
B7-J — Simulacion de desastres (chaos testing) CONTROLADA. Simula caidas (internet/AEAT/Verifactu/
email/SMS/API/DB/servidor central/VPN) abriendo el circuit breaker del servicio y midiendo la
recuperacion, SIN afectar datos reales. Registra resultado/tiempo/acciones en chaos_ejecuciones.
"""

import logging
import time
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.chaos")
ESCENARIOS = ("internet", "aeat", "verifactu", "sii", "email", "sms", "api", "db",
              "servidor_central", "vpn")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _registrar(eid, escenario, resultado, t_recuperacion, acciones, detalle=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO chaos_ejecuciones (id_empresa, escenario, resultado, "
                        "tiempo_recuperacion_seg, acciones, detalle) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eid, escenario, resultado, t_recuperacion, ",".join(acciones)[:255],
                         (detalle or "")[:1000]))
            conn.commit()
    except Exception as e:
        logger.error("_registrar chaos: %s", e)
    log_auditoria("resiliencia", "CHAOS", "chaos_ejecuciones", f"{escenario} {resultado} {t_recuperacion}s")


def simular(escenario, *, id_empresa=None, restaurar=True) -> dict:
    """Simula la caida de un servicio: abre su breaker, verifica fail-fast y mide recuperacion.
    NO toca datos reales; si restaurar=True, cierra el breaker al terminar."""
    eid = _emp(id_empresa)
    if escenario not in ESCENARIOS:
        raise ValueError(f"escenario invalido: {escenario}")
    from src.services.resiliencia import circuit_breaker as cb
    acciones, t0 = [], time.perf_counter()
    servicio = {"internet": "api", "servidor_central": "db", "vpn": "api"}.get(escenario, escenario)

    # 1) Provocar apertura del breaker (fallos hasta abrir).
    for _ in range(6):
        cb.registrar_fallo(servicio, id_empresa=eid)
    acciones.append("breaker_forzado")
    abierto = any(b["servicio"] == servicio for b in cb.abiertos(id_empresa=eid))
    acciones.append(f"breaker_abierto={abierto}")

    # 2) Verificar fail-fast (no permite llamadas).
    fail_fast = not cb.permitido(servicio, id_empresa=eid)
    acciones.append(f"fail_fast={fail_fast}")

    # 3) Watchdog detecta el breaker abierto.
    try:
        from src.services.resiliencia import resilience_watchdog
        diag = resilience_watchdog.diagnosticar(id_empresa=eid)
        acciones.append(f"watchdog_breakers={diag.get('breakers_abiertos')}")
    except Exception:
        pass

    # 4) Recuperacion.
    if restaurar:
        cb.resetear(servicio, id_empresa=eid)
        acciones.append("breaker_reseteado")
    t_rec = round(time.perf_counter() - t0, 3)
    ok = abierto and fail_fast
    _registrar(eid, escenario, "ok" if ok else "fallido", t_rec, acciones)
    return {"ok": ok, "escenario": escenario, "tiempo_recuperacion_seg": t_rec, "acciones": acciones}


def simular_offline_tienda(id_tienda, *, id_empresa=None) -> dict:
    """Simula que una tienda pierde conexion, opera offline y se recupera al reconectar."""
    eid = _emp(id_empresa)
    from src.services.resiliencia import edge_node, offline_store
    import uuid
    t0 = time.perf_counter()
    edge_node.registrar(eid, id_tienda)
    edge_node.entrar_offline(eid, id_tienda)
    # Opera offline: una venta local.
    idem = f"chaos-{uuid.uuid4().hex[:12]}"
    offline_store.set_stock(eid, "CHAOS_ART", 10, id_tienda=id_tienda)
    offline_store.registrar_venta(eid, idem, {"lineas": [{"codigo": "CHAOS_ART", "cantidad": 2}]}, 20,
                                  id_tienda=id_tienda)
    pend_antes = offline_store.pendientes_sync(eid, id_tienda=id_tienda)
    rec = edge_node.reconectar(eid, id_tienda)
    pend_despues = offline_store.pendientes_sync(eid, id_tienda=id_tienda)
    t_rec = round(time.perf_counter() - t0, 3)
    ok = sum(pend_antes.values()) > 0 and rec.get("ok")
    _registrar(eid, "offline_tienda", "ok" if ok else "fallido", t_rec,
               ["venta_offline", "reconexion", "sync"], f"antes={pend_antes} despues={pend_despues}")
    return {"ok": ok, "tiempo_recuperacion_seg": t_rec, "pendientes_antes": pend_antes,
            "pendientes_despues": pend_despues}


def historial(*, escenario=None, limite=100) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if escenario:
                cur.execute("SELECT * FROM chaos_ejecuciones WHERE escenario=%s ORDER BY fecha DESC LIMIT %s",
                            (escenario, int(limite)))
            else:
                cur.execute("SELECT * FROM chaos_ejecuciones ORDER BY fecha DESC LIMIT %s", (int(limite),))
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("historial chaos: %s", e)
        return []
