"""
Motor de distribucion (Fase 2, SUBFASE 2.1/2.3/2.10) — orquestacion.

Consume el Event Bus (drena `eventos` en estado PENDIENTE), decide destinatarios y politica,
y encola cada evento por destino en `distribucion_pendiente`. Los criticos se envian de
inmediato; los programados esperan a la ventana de mantenimiento. Las terminales offline
conservan sus eventos hasta reconectar (nunca se pierden). Ningun modulo ejecuta logica de
distribucion directamente: todo pasa por el bus.
"""

import logging
from datetime import datetime

from src.services.distribucion import (cola, config, destinatarios, politicas,
                                       terminales)

logger = logging.getLogger("distribucion.motor")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def procesar_eventos_pendientes(id_empresa=None, limite=500) -> dict:
    """Drena los eventos PENDIENTES del bus → los encola en distribucion por destino y los
    marca consumidos por el consumidor 'distribucion'. Devuelve {eventos, distribuciones}."""
    emp = _emp(id_empresa)
    res = {"eventos": 0, "distribuciones": 0}
    try:
        from src.services import eventos as EV
    except Exception as e:
        logger.error("bus no disponible: %s", e)
        return res
    evs = EV.buscar(id_empresa=emp, estado="PENDIENTE", limite=limite)
    for ev in evs:
        try:
            pol = politicas.politica(ev.get("tipo"), ev.get("prioridad"))
            dests = destinatarios.resolver(ev, pol, id_empresa=emp)
            prog = datetime.now() if pol["sincronizacion"] == "CRITICA" else config.proxima_ventana(emp)
            for d in dests:
                if cola.encolar(ev, d, sincronizacion=pol["sincronizacion"],
                                prioridad=ev.get("prioridad") or "MEDIA",
                                fecha_programada=prog, id_empresa=emp):
                    res["distribuciones"] += 1
            EV.consumir(ev["id"], id_empresa=emp, destino="distribucion",
                        detalle=f"encolado ({pol['sincronizacion']}, {len(dests)} destinos)")
            res["eventos"] += 1
        except Exception as e:
            logger.warning("procesar evento %s: %s", ev.get("id"), e)
    return res


def distribuir(id_empresa=None, sincronizacion=None, limite=1000) -> dict:
    """Envia las distribuciones cuya fecha_programada ya vencio. Terminal ONLINE → ENVIADO
    (+ ACK pendiente); terminal OFFLINE → permanece en cola (SUBFASE 2.10)."""
    emp = _emp(id_empresa)
    now = datetime.now()
    enviados, offline = 0, 0
    for f in cola.pendientes(sincronizacion=sincronizacion, estado="PENDIENTE", hasta=now,
                             id_empresa=emp, limite=limite):
        pi = f.get("proximo_intento")
        if pi and pi > now:
            continue
        idt = int(f.get("destino_tienda") or 0)
        if terminales.esta_online(idt, emp):
            if cola.marcar_enviado(f["id"], terminal=f["destino"], id_empresa=emp):
                enviados += 1
        else:
            offline += 1
    return {"enviados": enviados, "offline_pendientes": offline}


def distribuir_criticos(id_empresa=None) -> dict:
    return distribuir(id_empresa, sincronizacion="CRITICA")


def distribuir_programados(id_empresa=None) -> dict:
    """Ventana de mantenimiento: envia lo PROGRAMADO cuya hora ya llego."""
    return distribuir(id_empresa, sincronizacion="PROGRAMADA")


def procesar_reintentos(id_empresa=None, limite=1000) -> dict:
    """Reenvia las filas cuyo proximo_intento ya vencio (SUBFASE 2.6)."""
    emp = _emp(id_empresa)
    now = datetime.now()
    reintentados = 0
    for f in cola.pendientes(estado="PENDIENTE", id_empresa=emp, limite=limite):
        pi = f.get("proximo_intento")
        if pi and pi <= now and int(f.get("reintentos") or 0) > 0:
            idt = int(f.get("destino_tienda") or 0)
            if terminales.esta_online(idt, emp) and cola.marcar_enviado(
                    f["id"], terminal=f["destino"], id_empresa=emp):
                reintentados += 1
    return {"reintentados": reintentados}


def sincronizar_terminal(id_tienda, id_empresa=None, limite=5000) -> dict:
    """Al reconectar una terminal, se le entregan TODOS sus eventos pendientes (SUBFASE 2.10)."""
    emp = _emp(id_empresa)
    idt = int(id_tienda or 0)
    try:
        terminales.reconectar(idt, emp)
    except Exception as e:
        logger.debug("reconectar terminal %s: %s", idt, e)
    entregados = 0
    for f in cola.pendientes(estado="PENDIENTE", id_empresa=emp, limite=limite):
        if int(f.get("destino_tienda") or 0) == idt:
            if cola.marcar_enviado(f["id"], terminal=f["destino"], id_empresa=emp):
                entregados += 1
    return {"terminal": idt, "entregados": entregados}


def tick(id_empresa=None) -> dict:
    """Ciclo completo: drena bus → distribuye criticos → procesa reintentos. Idempotente."""
    return {
        "procesados": procesar_eventos_pendientes(id_empresa),
        "criticos": distribuir_criticos(id_empresa),
        "reintentos": procesar_reintentos(id_empresa),
    }
