"""
SAT-F — Email-to-ticket. Reutiliza correos_recibidos (IMAP de la rama Comunicaciones):
convierte correos entrantes no procesados en tickets y actualiza tickets desde respuestas
(detecta el codigo TKxxxxxx en el asunto). No duplica el correo: enlaza por ref_correo. Auditado.
"""

import logging
import re
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.email")
_RE_TICKET = re.compile(r"\bTK(\d{6})\b", re.IGNORECASE)


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _cliente_por_email(email, eid):
    if not email:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM clientes WHERE id_empresa=%s AND email=%s LIMIT 1", (eid, email))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception:
        return None


def procesar_correos(*, id_empresa=None) -> dict:
    """Convierte correos recibidos no procesados en tickets (o comentarios si referencian un ticket)."""
    eid = _emp(id_empresa)
    from src.services.sat import tickets
    creados, actualizados = [], []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Solo correos que aun no han generado ticket (ref_correo no usado en tickets).
            cur.execute("SELECT cr.id, cr.remitente, cr.asunto, cr.cuerpo FROM correos_recibidos cr "
                        "WHERE cr.id_empresa=%s AND cr.id NOT IN "
                        "(SELECT ref_correo FROM tickets WHERE ref_correo IS NOT NULL AND id_empresa=%s) "
                        "ORDER BY cr.id DESC LIMIT 200", (eid, eid))
            correos = [(r if isinstance(r, dict) else {"id": r[0], "remitente": r[1], "asunto": r[2], "cuerpo": r[3]})
                       for r in cur.fetchall()]
    except Exception as e:
        logger.error("procesar_correos/lectura: %s", e)
        return {"creados": [], "actualizados": []}
    for c in correos:
        asunto = c.get("asunto") or "(sin asunto)"
        m = _RE_TICKET.search(asunto)
        if m:
            # Respuesta a un ticket existente -> comentario del cliente.
            tid = _ticket_por_codigo(f"TK{m.group(1)}", eid)
            if tid:
                tickets.comentar(tid, c.get("cuerpo") or "", autor=c.get("remitente"),
                                 es_cliente=True, id_empresa=eid)
                # Si estaba resuelto/cerrado, reabrir.
                t = tickets.obtener(tid)
                if t and t.get("estado") in ("resuelto", "cerrado"):
                    tickets.cambiar_estado(tid, "reabierto", id_empresa=eid)
                actualizados.append(tid)
                continue
        # Nuevo ticket desde correo.
        cliente = _cliente_por_email(c.get("remitente"), eid)
        tid = tickets.crear_ticket(asunto, descripcion=c.get("cuerpo"), id_cliente=cliente, canal="email",
                                   email_origen=c.get("remitente"), ref_correo=c.get("id"), id_empresa=eid)
        if tid:
            creados.append(tid)
    return {"creados": creados, "actualizados": actualizados}


def _ticket_por_codigo(codigo, eid):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM tickets WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception:
        return None


def _job_email_ticket(id_empresa):
    r = procesar_correos(id_empresa=id_empresa)
    return f"creados={len(r['creados'])} actualizados={len(r['actualizados'])}"


def registrar_jobs_email(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("sat_email_ticket", _job_email_ticket)
    scheduler.registrar_job("sat_email_ticket", intervalo_horas=1,
                            descripcion="Email-to-ticket", id_empresa=id_empresa)
