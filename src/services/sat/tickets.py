"""
SAT-A/C — Tickets de soporte (ciclo + comentarios) + colas + asignacion (manual/automatica).
SLA calculado desde el contrato del cliente (SAT-B). Multiempresa, auditado.

Estados: abierto/asignado/en_proceso/pendiente/resuelto/cerrado/reabierto.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.tickets")
ESTADOS = ("abierto", "asignado", "en_proceso", "pendiente", "resuelto", "cerrado", "reabierto")
PRIORIDADES = ("baja", "media", "alta", "critica")
_TRANS = {
    "abierto": {"asignado", "en_proceso", "cerrado"},
    "asignado": {"en_proceso", "pendiente", "cerrado"},
    "en_proceso": {"pendiente", "resuelto", "cerrado"},
    "pendiente": {"en_proceso", "resuelto", "cerrado"},
    "resuelto": {"cerrado", "reabierto"},
    "cerrado": {"reabierto"},
    "reabierto": {"en_proceso", "asignado", "resuelto", "cerrado"},
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_ticket(asunto, *, descripcion=None, id_cliente=None, canal="manual", prioridad="media",
                 categoria=None, id_cola=None, email_origen=None, ref_correo=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if prioridad not in PRIORIDADES:
        prioridad = "media"
    # SLA desde el contrato del cliente (si lo hay).
    id_contrato, sla_venc = _resolver_sla(id_cliente, prioridad, eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO tickets (id_empresa, asunto, descripcion, id_cliente, canal, prioridad, "
                        "categoria, id_cola, id_contrato, sla_vencimiento, email_origen, ref_correo) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, asunto, descripcion, id_cliente, canal, prioridad, categoria, id_cola,
                         id_contrato, sla_venc, email_origen, ref_correo))
            tid = cur.lastrowid
            cur.execute("UPDATE tickets SET codigo=%s WHERE id=%s", (f"TK{tid:06d}", tid))
            conn.commit()
        log_auditoria("sat", "TICKET_CREADO", "tickets", f"ticket={tid} {prioridad} canal={canal}")
        _notificar(tid, asunto, prioridad, eid)
        # Auto-asignacion si la cola lo permite.
        if id_cola:
            _auto_asignar(tid, id_cola, eid)
        return tid
    except Exception as e:
        logger.error("crear_ticket: %s", e)
        return None


def _resolver_sla(id_cliente, prioridad, eid):
    if not id_cliente:
        return None, None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT c.id, s.horas_resolucion FROM contratos_servicio c "
                        "LEFT JOIN sla_servicio s ON s.id=c.id_sla WHERE c.id_empresa=%s AND c.id_cliente=%s "
                        "AND c.activo=1 ORDER BY c.id DESC LIMIT 1", (eid, id_cliente))
            r = cur.fetchone()
        if not r:
            return None, None
        r = list(r.values()) if isinstance(r, dict) else r
        horas = int(r[1] or 72)
        # Prioridad critica reduce el plazo a la mitad.
        if prioridad == "critica":
            horas = max(1, horas // 2)
        return r[0], _dt.datetime.now() + _dt.timedelta(hours=horas)
    except Exception as e:
        logger.debug("_resolver_sla: %s", e)
        return None, None


def comentar(id_ticket, cuerpo, *, autor=None, es_cliente=False, interno=False, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ticket_comentarios (id_empresa, id_ticket, autor, es_cliente, interno, cuerpo) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (eid, id_ticket, autor, 1 if es_cliente else 0,
                                                       1 if interno else 0, cuerpo))
            cid = cur.lastrowid
            # Primera respuesta del agente marca fecha_primera_respuesta.
            if not es_cliente and not interno:
                cur.execute("UPDATE tickets SET fecha_primera_respuesta=COALESCE(fecha_primera_respuesta, NOW()) "
                            "WHERE id=%s", (id_ticket,))
            conn.commit()
        return cid
    except Exception as e:
        logger.error("comentar: %s", e)
        return None


def cambiar_estado(id_ticket, nuevo, *, id_empresa=None) -> dict:
    if nuevo not in ESTADOS:
        raise ValueError(f"estado invalido: {nuevo}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM tickets WHERE id=%s", (id_ticket,))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "error": "ticket inexistente"}
            actual = r[0] if not isinstance(r, dict) else list(r.values())[0]
            if nuevo != actual and nuevo not in _TRANS.get(actual, set()):
                return {"ok": False, "error": f"transicion {actual}->{nuevo} no permitida"}
            extra = ""
            if nuevo == "resuelto":
                extra = ", fecha_resolucion=NOW()"
            elif nuevo == "cerrado":
                extra = ", fecha_cierre=NOW()"
            elif nuevo == "reabierto":
                extra = ", fecha_resolucion=NULL, fecha_cierre=NULL"
            cur.execute(f"UPDATE tickets SET estado=%s{extra} WHERE id=%s", (nuevo, id_ticket))
            conn.commit()
        log_auditoria("sat", f"TICKET_{nuevo.upper()}", "tickets", f"ticket={id_ticket}")
        return {"ok": True, "estado": nuevo}
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado ticket: %s", e)
        return {"ok": False, "error": str(e)}


def asignar(id_ticket, tecnico, *, modo="manual", id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE tickets SET tecnico=%s, estado=CASE WHEN estado='abierto' THEN 'asignado' "
                        "ELSE estado END WHERE id=%s", (tecnico, id_ticket))
            cur.execute("INSERT INTO asignaciones_ticket (id_empresa, id_ticket, tecnico, modo) "
                        "VALUES (%s,%s,%s,%s)", (eid, id_ticket, tecnico, modo))
            conn.commit()
        log_auditoria("sat", "TICKET_ASIGNADO", "tickets", f"ticket={id_ticket} tecnico={tecnico} {modo}")
        return {"ok": True, "tecnico": tecnico}
    except Exception as e:
        logger.error("asignar: %s", e)
        return {"ok": False, "error": str(e)}


def _auto_asignar(id_ticket, id_cola, eid):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT auto_asignar, responsable FROM colas_soporte WHERE id=%s", (id_cola,))
            r = cur.fetchone()
        if r:
            r = list(r.values()) if isinstance(r, dict) else r
            if r[0] and r[1]:
                asignar(id_ticket, r[1], modo="automatica", id_empresa=eid)
    except Exception as e:
        logger.debug("_auto_asignar: %s", e)


def crear_cola(codigo, nombre, *, auto_asignar=False, responsable=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO colas_soporte (id_empresa, codigo, nombre, auto_asignar, responsable) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "auto_asignar=VALUES(auto_asignar), responsable=VALUES(responsable)",
                        (eid, codigo, nombre, 1 if auto_asignar else 0, responsable))
            cur.execute("SELECT id FROM colas_soporte WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            cid = cur.fetchone()
            conn.commit()
        return cid[0] if not isinstance(cid, dict) else list(cid.values())[0]
    except Exception as e:
        logger.error("crear_cola: %s", e)
        return None


def obtener(id_ticket) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tickets WHERE id=%s", (id_ticket,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener ticket: %s", e)
        return None


def listar(*, estado=None, prioridad=None, tecnico=None, id_cliente=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM tickets WHERE id_empresa=%s"
    p = [eid]
    for col, val in (("estado", estado), ("prioridad", prioridad), ("tecnico", tecnico), ("id_cliente", id_cliente)):
        if val is not None:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar tickets: %s", e)
        return []


def _notificar(tid, asunto, prioridad, eid):
    try:
        from src.services import notificaciones
        notificaciones.emitir("sat", f"Nuevo ticket {tid}", asunto, modulo="sat",
                              prioridad="critica" if prioridad == "critica" else "alta",
                              roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
    except Exception:
        pass
