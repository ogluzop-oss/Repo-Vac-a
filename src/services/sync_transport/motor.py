"""
Motor de transporte y sincronizacion fisica (Fase 4, SUBFASE 4.1/4.5/4.13).

Convierte el ACK LOGICO (Fase 2) en transporte + recepcion + aplicacion + ACK REAL:

    distribucion_pendiente (ENVIADO)
        -> paquete diferencial comprimido (paquetes)
        -> transporte fisico (registry: local/LAN/VPN/...)
        -> aplicacion idempotente (replicacion) con REANUDACION desde offset
        -> ACK real (distribucion.cola.confirmar = APLICADO)
        -> control de versiones (terminal_versiones)
    todo instrumentado en sync_sesiones (observabilidad 4.13).

Reutiliza la infra de Fases 1-3; no la rediseña. Multiempresa/multitienda. Bulletproof.
"""

import json
import logging
import time
import uuid as _uuid

from src.services.replicacion import aplicador
from src.services.sync_transport import paquetes, registry, versiones

logger = logging.getLogger("sync_transport.motor")


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


def _dicts(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Observabilidad (sync_sesiones) ───────────────────────────────────────────
def _iniciar_sesion(emp, origen, destino, transporte):
    try:
        from src.db.conexion import obtener_conexion
        u = str(_uuid.uuid4())
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO sync_sesiones (uuid, id_empresa, origen_tienda, destino_tienda, "
                        "transporte, estado) VALUES (%s,%s,%s,%s,%s,'EN_CURSO')",
                        (u, emp, int(origen or 0), int(destino or 0), transporte))
            sid = cur.lastrowid
            c.commit()
        return {"id": sid, "t0": time.perf_counter()}
    except Exception as e:
        logger.debug("iniciar sesion: %s", e)
        return {"id": None, "t0": time.perf_counter()}


def _cerrar_sesion(ses, estado, *, bytes=0, num_eventos=0, num_paquetes=0, error=None):
    if not ses or ses.get("id") is None:
        return
    try:
        from src.db.conexion import obtener_conexion
        dur = int((time.perf_counter() - ses["t0"]) * 1000)
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE sync_sesiones SET fin=NOW(), duracion_ms=%s, bytes=%s, num_eventos=%s, "
                        "num_paquetes=%s, estado=%s, error=%s WHERE id=%s",
                        (dur, int(bytes), int(num_eventos), int(num_paquetes), estado,
                         (error or "")[:255] or None, ses["id"]))
            c.commit()
    except Exception as e:
        logger.debug("cerrar sesion: %s", e)


# ── Reunion diferencial (cambios pendientes para el destino) ──────────────────
def _pendientes_para(emp, idt, limite):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.destino, d.uuid_evento, d.id_evento, d.tipo_evento, d.prioridad, "
                "d.payload, e.ref_entidad, e.ref_id, e.usuario, e.origen "
                "FROM distribucion_pendiente d LEFT JOIN eventos e "
                "  ON e.id=d.id_evento AND e.id_empresa=d.id_empresa "
                "WHERE d.id_empresa=%s AND d.destino_tienda=%s AND d.estado IN ('PENDIENTE','ENVIADO') "
                "ORDER BY FIELD(d.prioridad,'CRITICA','ALTA','MEDIA','BAJA','INFORMATIVA'), d.id "
                "LIMIT %s", (emp, int(idt), int(limite)))
            return _dicts(cur)
    except Exception as e:
        logger.error("pendientes_para: %s", e)
        return []


def _a_cambio(f):
    payload = f.get("payload")
    try:
        payload = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        pass
    return {"id_evento": f.get("id_evento"), "uuid": f.get("uuid_evento"),
            "tipo": f.get("tipo_evento"), "ref_entidad": f.get("ref_entidad"),
            "ref_id": f.get("ref_id"), "usuario": f.get("usuario"), "origen": f.get("origen"),
            "payload": payload, "distribucion": f.get("id")}


# ── Aplicacion con reanudacion (4.5) ──────────────────────────────────────────
def _aplicar_paquete(id_paquete, id_empresa=None) -> dict:
    """Aplica los cambios de un paquete desde `offset_aplicado`. Si falla, deja el offset para
    REANUDAR mas tarde (nunca reinicia desde cero)."""
    emp = _emp(id_empresa)
    paq = paquetes.cargar(id_paquete, emp)
    if not paq:
        return {"aplicados": 0, "estado": "ERROR", "error": "paquete inexistente"}
    if not paq.get("integro"):
        _estado_paquete(emp, id_paquete, "ERROR", error="hash no coincide")
        return {"aplicados": 0, "estado": "ERROR", "error": "integridad"}
    cambios = paq.get("cambios") or []
    off = int(paq.get("offset_aplicado") or 0)
    _estado_paquete(emp, id_paquete, "APLICANDO")
    aplicados = 0
    for i in range(off, len(cambios)):
        r = aplicador.aplicar(cambios[i], id_empresa=emp)
        if r == "error":
            _offset_paquete(emp, id_paquete, i, estado="ERROR")   # reanudable desde i
            return {"aplicados": aplicados, "estado": "ERROR", "offset": i}
        aplicados += 1
        _offset_paquete(emp, id_paquete, i + 1)
    _estado_paquete(emp, id_paquete, "APLICADO", aplicado=True)
    return {"aplicados": aplicados, "estado": "APLICADO", "offset": len(cambios)}


def _estado_paquete(emp, pid, estado, *, aplicado=False, error=None):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if aplicado:
                cur.execute("UPDATE sync_paquetes SET estado=%s, aplicado_en=NOW() WHERE id=%s AND id_empresa=%s",
                            (estado, pid, emp))
            else:
                cur.execute("UPDATE sync_paquetes SET estado=%s, error=%s WHERE id=%s AND id_empresa=%s",
                            (estado, (error or None), pid, emp))
            c.commit()
    except Exception as e:
        logger.debug("estado_paquete: %s", e)


def _offset_paquete(emp, pid, offset, estado=None):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if estado:
                cur.execute("UPDATE sync_paquetes SET offset_aplicado=%s, estado=%s WHERE id=%s AND id_empresa=%s",
                            (int(offset), estado, pid, emp))
            else:
                cur.execute("UPDATE sync_paquetes SET offset_aplicado=%s WHERE id=%s AND id_empresa=%s",
                            (int(offset), pid, emp))
            c.commit()
    except Exception as e:
        logger.debug("offset_paquete: %s", e)


# ── API PUBLICA ───────────────────────────────────────────────────────────────
def sincronizar(destino_tienda, id_empresa=None, *, transporte="local", origen_tienda=0,
                prioridad="MEDIA", limite=1000) -> dict:
    """Sincroniza fisicamente los cambios pendientes hacia una terminal. Bulletproof."""
    emp = _emp(id_empresa)
    idt = int(destino_tienda or 0)
    ses = _iniciar_sesion(emp, origen_tienda, idt, transporte)
    try:
        filas = _pendientes_para(emp, idt, limite)
        if not filas:
            _cerrar_sesion(ses, "COMPLETADA")
            return {"destino": idt, "enviados": 0, "aplicados": 0, "bytes": 0, "paquete": None}
        cambios = [_a_cambio(f) for f in filas]
        paq = paquetes.construir(cambios, origen_tienda=origen_tienda, destino_tienda=idt,
                                 prioridad=prioridad, id_empresa=emp, transporte=transporte)
        if not paq:
            _cerrar_sesion(ses, "ERROR", error="no se pudo construir paquete")
            return {"destino": idt, "error": "paquete"}
        T = registry.obtener(transporte)
        if not T or not T.disponible(idt, emp):
            _cerrar_sesion(ses, "OFFLINE", error="terminal offline")
            return {"destino": idt, "estado": "OFFLINE", "paquete": paq["uuid"]}
        res = T.enviar(paq, idt, emp)
        if not res.ok:
            _cerrar_sesion(ses, "ERROR", error=res.detalle)
            return {"destino": idt, "error": res.detalle, "paquete": paq["uuid"]}
        apl = _aplicar_paquete(paq["id"], emp)
        if apl["estado"] == "APLICADO":
            for f in filas:
                try:
                    from src.services.distribucion import cola
                    cola.confirmar(f["id"], terminal=f["destino"], estado="APLICADO", id_empresa=emp)
                except Exception:
                    pass
            versiones.actualizar(emp, idt, ultimo_paquete=paq["uuid"], hash=paq["hash"])
        _cerrar_sesion(ses, ("COMPLETADA" if apl["estado"] == "APLICADO" else "ERROR"),
                       bytes=paq["bytes_comprimido"], num_eventos=len(cambios), num_paquetes=1,
                       error=(None if apl["estado"] == "APLICADO" else "aplicacion incompleta"))
        return {"destino": idt, "enviados": len(filas), "aplicados": apl["aplicados"],
                "estado_paquete": apl["estado"], "bytes": paq["bytes_comprimido"],
                "ratio_compresion": paq["ratio"], "paquete": paq["uuid"]}
    except Exception as e:
        logger.error("sincronizar(%s): %s", idt, e)
        _cerrar_sesion(ses, "ERROR", error=str(e))
        return {"destino": idt, "error": str(e)}


def reanudar(id_empresa=None, limite=200) -> dict:
    """Reanuda paquetes con aplicacion incompleta (SUBFASE 4.5) desde su offset. Nunca desde cero."""
    emp = _emp(id_empresa)
    reanudados = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id FROM sync_paquetes WHERE id_empresa=%s AND estado IN "
                        "('APLICANDO','ERROR','RECIBIDO') ORDER BY id LIMIT %s", (emp, int(limite)))
            ids = [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
        for pid in ids:
            r = _aplicar_paquete(pid, emp)
            if r["estado"] == "APLICADO":
                reanudados += 1
    except Exception as e:
        logger.error("reanudar: %s", e)
    return {"reanudados": reanudados}


def sincronizar_todas(id_empresa=None, *, transporte="local") -> dict:
    """Sincroniza todas las terminales de la empresa (barrido)."""
    emp = _emp(id_empresa)
    res = {}
    try:
        from src.services.distribucion import terminales
        for t in terminales.listar(emp):
            idt = int(t.get("id_tienda") or 0)
            res[idt] = sincronizar(idt, emp, transporte=transporte)
    except Exception as e:
        logger.error("sincronizar_todas: %s", e)
    return res
