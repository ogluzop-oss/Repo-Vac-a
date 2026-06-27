"""
CRM-F — CRM SaaS: funnel de venta del propio Smart Manager.
Fases: lead -> demo -> prueba -> cliente. Al convertir, enlaza con la empresa SaaS creada
(empresa_licencia/suscripciones de la rama SaaS, sin modificarlas). Auditado.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion

logger = logging.getLogger("crm.saas")
FASES = ("lead", "demo", "prueba", "cliente", "perdido")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_lead_saas(nombre, *, email=None, plan_interes=None, valor_estimado=0) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO crm_saas_funnel (nombre, email, plan_interes, valor_estimado, fase) "
                        "VALUES (%s,%s,%s,%s,'lead')", (nombre, email, plan_interes, valor_estimado))
            fid = cur.lastrowid
            conn.commit()
        log_auditoria("crm_saas", "CRM_SAAS_LEAD", "crm_saas_funnel", f"id={fid} {nombre}")
        return fid
    except Exception as e:
        logger.error("crear_lead_saas: %s", e)
        return None


def avanzar_fase(id_funnel, fase) -> bool:
    if fase not in FASES:
        raise ValueError(f"fase invalida: {fase}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_saas_funnel SET fase=%s WHERE id=%s", (fase, id_funnel))
            conn.commit()
        log_auditoria("crm_saas", "CRM_SAAS_FASE", "crm_saas_funnel", f"id={id_funnel}->{fase}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("avanzar_fase: %s", e)
        return False


def convertir_a_cliente_saas(id_funnel, id_empresa_creada) -> dict:
    """Marca el funnel como cliente y lo enlaza con la empresa SaaS recien creada."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_saas_funnel SET fase='cliente', id_empresa_creada=%s, "
                        "fecha_conversion=%s WHERE id=%s", (id_empresa_creada, _dt.datetime.now(), id_funnel))
            conn.commit()
        log_auditoria("crm_saas", "CRM_SAAS_CONVERSION", "crm_saas_funnel",
                      f"id={id_funnel} empresa={id_empresa_creada}")
        return {"ok": True, "id_empresa": id_empresa_creada}
    except Exception as e:
        logger.error("convertir_a_cliente_saas: %s", e)
        return {"ok": False, "error": str(e)}


def listar(fase=None, limite=500) -> list:
    q = "SELECT * FROM crm_saas_funnel"
    p = []
    if fase:
        q += " WHERE fase=%s"; p.append(fase)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def embudo() -> dict:
    """Conteo por fase del funnel SaaS (para el dashboard)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fase, COUNT(*) FROM crm_saas_funnel GROUP BY fase")
            return {(r[0] if not isinstance(r, dict) else list(r.values())[0]):
                    (r[1] if not isinstance(r, dict) else list(r.values())[1]) for r in cur.fetchall()}
    except Exception as e:
        logger.error("embudo: %s", e)
        return {}
