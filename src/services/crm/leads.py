"""
CRM-A — Leads. Captacion, almacenamiento, clasificacion, estados y conversion a cliente.
Multiempresa, auditado. Estados: nuevo/contactado/calificado/no_interesado/convertido/perdido.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.leads")
ESTADOS = ("nuevo", "contactado", "calificado", "no_interesado", "convertido", "perdido")
PRIORIDADES = ("baja", "normal", "alta")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_lead(nombre, *, empresa=None, email=None, telefono=None, fuente=None,
               valor_estimado=0, prioridad="normal", responsable=None, etiquetas=None,
               id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO crm_leads (id_empresa, nombre, empresa, email, telefono, fuente, "
                        "valor_estimado, prioridad, responsable, etiquetas) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, nombre, empresa, email, telefono, fuente, valor_estimado,
                         prioridad if prioridad in PRIORIDADES else "normal", responsable, etiquetas))
            lid = cur.lastrowid
            conn.commit()
        log_auditoria("crm", "CRM_LEAD_CREATED", "crm_leads", f"lead={lid} {nombre}")
        return lid
    except Exception as e:
        logger.error("crear_lead: %s", e)
        return None


def actualizar_lead(id_lead, **campos) -> bool:
    permitidos = ("nombre", "empresa", "email", "telefono", "fuente", "estado", "valor_estimado",
                  "prioridad", "responsable", "score", "etiquetas", "fecha_ultimo_contacto")
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    if "estado" in sets and sets["estado"] not in ESTADOS:
        raise ValueError(f"estado invalido: {sets['estado']}")
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE crm_leads SET {cols} WHERE id=%s", (*sets.values(), id_lead))
            conn.commit()
        log_auditoria("crm", "CRM_LEAD_UPDATED", "crm_leads", f"lead={id_lead} {list(sets)}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("actualizar_lead: %s", e)
        return False


def listar_leads(*, estado=None, responsable=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM crm_leads WHERE id_empresa=%s"
    p = [eid]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    if responsable is not None:
        q += " AND responsable=%s"; p.append(responsable)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_leads: %s", e)
        return []


def obtener_lead(id_lead) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM crm_leads WHERE id=%s", (id_lead,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_lead: %s", e)
        return None


def convertir_a_cliente(id_lead, *, id_empresa=None) -> dict:
    """Convierte un lead en cliente real (tabla clientes) y marca el lead como convertido."""
    eid = _emp(id_empresa)
    lead = obtener_lead(id_lead)
    if not lead:
        return {"ok": False, "error": "lead inexistente"}
    if lead.get("estado") == "convertido" and lead.get("id_cliente"):
        return {"ok": True, "id_cliente": lead["id_cliente"], "ya_convertido": True}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO clientes (nombre, email, telefono, id_empresa, estado) "
                        "VALUES (%s,%s,%s,%s,'activo')",
                        (lead.get("empresa") or lead["nombre"], lead.get("email"),
                         lead.get("telefono"), eid))
            cid = cur.lastrowid
            cur.execute("UPDATE crm_leads SET estado='convertido', id_cliente=%s WHERE id=%s", (cid, id_lead))
            conn.commit()
        log_auditoria("crm", "CRM_LEAD_CONVERTED", "crm_leads", f"lead={id_lead} cliente={cid}")
        return {"ok": True, "id_cliente": cid}
    except Exception as e:
        logger.error("convertir_a_cliente: %s", e)
        return {"ok": False, "error": str(e)}
