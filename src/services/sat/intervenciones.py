"""
SAT-D — Intervenciones (visitas/actuaciones) + partes tecnicos. Reutiliza calendario_eventos y
crm_actividades (no duplica): cada intervencion crea opcionalmente un evento de calendario. Auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.intervenciones")
TIPOS = ("visita", "remota", "telefonica", "taller")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def registrar_intervencion(*, id_ticket=None, id_ot=None, tecnico=None, tipo="visita",
                           descripcion=None, horas=0, fecha=None, crear_evento=False, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        tipo = "visita"
    ref_evento = ref_actividad = None
    if crear_evento and fecha:
        try:
            from src.services import calendario
            ref_evento = calendario.crear_evento(f"[SAT] {descripcion or 'Intervencion'}", fecha, tipo="visita",
                                                 creado_por=tecnico, id_empresa=eid)
        except Exception as e:
            logger.debug("calendario: %s", e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO intervenciones (id_empresa, id_ticket, id_ot, tecnico, tipo, descripcion, "
                        "horas, ref_evento, ref_actividad) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_ticket, id_ot, tecnico, tipo, descripcion, horas, ref_evento, ref_actividad))
            iid = cur.lastrowid
            conn.commit()
        log_auditoria("sat", "SAT_INTERVENCION", "intervenciones", f"interv={iid} ticket={id_ticket} ot={id_ot}")
        return iid
    except Exception as e:
        logger.error("registrar_intervencion: %s", e)
        return None


def crear_parte(id_intervencion, descripcion, *, firmado=False, ruta_pdf=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO partes_tecnicos (id_empresa, id_intervencion, descripcion, firmado, ruta_pdf) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, id_intervencion, descripcion, 1 if firmado else 0, ruta_pdf))
            pid = cur.lastrowid
            conn.commit()
        log_auditoria("sat", "SAT_PARTE", "partes_tecnicos", f"parte={pid} interv={id_intervencion}")
        return pid
    except Exception as e:
        logger.error("crear_parte: %s", e)
        return None


def listar(*, id_ticket=None, id_ot=None, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM intervenciones WHERE id_empresa=%s"
    p = [eid]
    if id_ticket is not None:
        q += " AND id_ticket=%s"; p.append(id_ticket)
    if id_ot is not None:
        q += " AND id_ot=%s"; p.append(id_ot)
    q += " ORDER BY fecha DESC"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar intervenciones: %s", e)
        return []
