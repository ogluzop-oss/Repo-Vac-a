"""
CAL-C — CAPA: acciones correctivas y preventivas con seguimiento y eficacia. Auditado.
Al cerrar todas las acciones de una NC, esta puede pasar a 'accionada'.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.capa")
TIPOS = ("correctiva", "preventiva")
ESTADOS = ("abierta", "en_curso", "cerrada", "cancelada")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_accion(descripcion, *, tipo="correctiva", id_nc=None, responsable=None,
                 fecha_limite=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO acciones_correctivas (id_empresa, id_nc, tipo, descripcion, responsable, "
                        "fecha_limite) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eid, id_nc, tipo, descripcion[:255], responsable, fecha_limite))
            aid = cur.lastrowid
            conn.commit()
        log_auditoria("calidad", "CAPA_CREATED", "acciones_correctivas", f"capa={aid} {tipo} nc={id_nc}")
        return aid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_accion: %s", e)
        return None


def cambiar_estado(id_capa, estado, *, eficacia=None, id_empresa=None) -> dict:
    if estado not in ESTADOS:
        raise ValueError(f"estado invalido: {estado}")
    cierre = ", fecha_cierre=%s, eficacia=%s" if estado == "cerrada" else ""
    params = [estado]
    if cierre:
        params += [_dt.datetime.now(), eficacia]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE acciones_correctivas SET estado=%s{cierre} WHERE id=%s", (*params, id_capa))
            cur.execute("SELECT id_nc FROM acciones_correctivas WHERE id=%s", (id_capa,))
            r = cur.fetchone()
            id_nc = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            conn.commit()
        log_auditoria("calidad", f"CAPA_{estado.upper()}", "acciones_correctivas", f"capa={id_capa}")
        # Si todas las acciones de la NC estan cerradas -> NC accionada.
        if estado == "cerrada" and id_nc:
            _avanzar_nc_si_completa(id_nc, id_empresa=_emp(id_empresa))
        return {"ok": True, "estado": estado}
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado CAPA: %s", e)
        return {"ok": False, "error": str(e)}


def _avanzar_nc_si_completa(id_nc, *, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM acciones_correctivas WHERE id_nc=%s AND estado NOT IN "
                        "('cerrada','cancelada')", (id_nc,))
            pendientes = cur.fetchone()
            pendientes = pendientes[0] if not isinstance(pendientes, dict) else list(pendientes.values())[0]
        if pendientes == 0:
            from src.services.calidad import no_conformidades
            nc = no_conformidades.obtener(id_nc)
            if nc and nc.get("estado") in ("abierta", "en_analisis"):
                if nc.get("estado") == "abierta":
                    no_conformidades.cambiar_estado(id_nc, "en_analisis", id_empresa=id_empresa)
                no_conformidades.cambiar_estado(id_nc, "accionada", id_empresa=id_empresa)
    except Exception as e:
        logger.debug("_avanzar_nc_si_completa: %s", e)


def listar(*, id_nc=None, tipo=None, estado=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM acciones_correctivas WHERE id_empresa=%s"
    p = [eid]
    for col, val in (("id_nc", id_nc), ("tipo", tipo), ("estado", estado)):
        if val is not None:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY creado_en DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar CAPA: %s", e)
        return []
