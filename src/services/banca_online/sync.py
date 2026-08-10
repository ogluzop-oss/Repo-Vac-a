"""
Sincronización bancaria en vivo → conciliación.

Obtiene los movimientos reales de la entidad (vía `BancaGateway`) y los IMPORTA al motor de conciliación
existente (`db.conciliacion_bancaria`: extracto + líneas idempotentes por hash), lanzando después la
conciliación automática (`tesoreria.conciliacion.conciliar_automatico`). No duplica nada: reutiliza el ciclo
de extractos/conciliación ya validado (N7). Degradable: sin conexión real no importa nada.
"""

import logging

from src.db.conexion import log_auditoria
from src.services.banca_online import config

logger = logging.getLogger("banca.sync")


def _emp(id_empresa=None):
    return config._emp(id_empresa)


def sincronizar(id_cuenta, *, desde=None, hasta=None, id_empresa=None, transport=None):
    """Descarga los movimientos y los importa como extracto (+ conciliación automática).
    Devuelve {ok, importados, extracto, conciliados}."""
    eid = _emp(id_empresa)
    gw = config.gateway(id_cuenta, eid, transport=transport)
    movimientos = gw.obtener_movimientos(desde, hasta)
    config.marcar_sync(id_cuenta, eid)
    if not movimientos:
        return {"ok": True, "importados": 0, "extracto": None, "conciliados": 0}

    from src.db import conciliacion_bancaria as CB
    ext = CB.crear_extracto(id_cuenta, "ONLINE", nombre_fichero="banca_online", id_empresa=eid)
    if not ext:
        return {"ok": False, "error": "no se pudo crear el extracto"}
    n = 0
    for m in movimientos:
        if CB.anadir_linea(ext, m.get("fecha"), m.get("importe") or 0, concepto=m.get("concepto"),
                           referencia=m.get("referencia"), id_empresa=eid):
            n += 1
    try:
        CB.actualizar_num_lineas(ext, eid)
    except Exception:
        pass

    conciliados = 0
    try:
        from src.services.tesoreria import conciliacion as CC
        res = CC.conciliar_automatico(ext, id_cuenta=id_cuenta, id_empresa=eid) or {}
        conciliados = int(res.get("conciliadas") or res.get("conciliados") or res.get("emparejadas") or 0)
    except Exception as e:
        logger.debug("conciliar_automatico: %s", e)

    log_auditoria("tesoreria", "BANCA_ONLINE_SYNC", "banca_conexiones",
                  f"cuenta={id_cuenta} extracto={ext} importados={n} conciliados={conciliados}")
    return {"ok": True, "importados": n, "extracto": ext, "conciliados": conciliados}
