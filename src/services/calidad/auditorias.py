"""
CAL-D — Auditorias de calidad (interna/externa/proveedor/proceso) + hallazgos.
Un hallazgo puede generar una NC. Planificacion y resultados. Auditado.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.auditorias")
TIPOS = ("interna", "externa", "proveedor", "proceso")
ESTADOS = ("planificada", "en_curso", "realizada", "cerrada", "cancelada")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def planificar(tipo, alcance, *, fecha_plan=None, auditor=None, id_proveedor=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO auditorias_calidad (id_empresa, tipo, alcance, id_proveedor, auditor, "
                        "fecha_plan) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eid, tipo, alcance, id_proveedor, auditor, fecha_plan))
            aid = cur.lastrowid
            cur.execute("UPDATE auditorias_calidad SET codigo=%s WHERE id=%s", (f"AUD{aid:05d}", aid))
            conn.commit()
        log_auditoria("calidad", "AUDIT_PLANIFICADA", "auditorias_calidad", f"aud={aid} {tipo}")
        return aid
    except ValueError:
        raise
    except Exception as e:
        logger.error("planificar auditoria: %s", e)
        return None


def registrar_hallazgo(id_auditoria, descripcion, *, severidad="media", generar_nc=False, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    nc = None
    if generar_nc:
        from src.services.calidad import no_conformidades
        nc = no_conformidades.abrir(f"Hallazgo auditoria {id_auditoria}: {descripcion}", origen="interna",
                                    severidad=severidad, id_empresa=eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO hallazgos_auditoria (id_empresa, id_auditoria, descripcion, severidad, id_nc) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, id_auditoria, descripcion[:255], severidad, nc))
            hid = cur.lastrowid
            conn.commit()
        log_auditoria("calidad", "AUDIT_HALLAZGO", "hallazgos_auditoria", f"aud={id_auditoria} h={hid}")
        return {"ok": True, "hallazgo": hid, "no_conformidad": nc}
    except Exception as e:
        logger.error("registrar_hallazgo: %s", e)
        return {"ok": False, "error": str(e)}


def cerrar(id_auditoria, *, resultado="conforme", id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE auditorias_calidad SET estado='realizada', fecha_realizada=%s, resultado=%s "
                        "WHERE id=%s", (_dt.date.today(), resultado, id_auditoria))
            conn.commit()
        log_auditoria("calidad", "AUDIT_REALIZADA", "auditorias_calidad", f"aud={id_auditoria} {resultado}")
        return True
    except Exception as e:
        logger.error("cerrar auditoria: %s", e)
        return False


def listar(*, tipo=None, estado=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM auditorias_calidad WHERE id_empresa=%s"
    p = [eid]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY id DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar auditorias: %s", e)
        return []
