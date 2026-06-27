"""
CRM-D — Actividades comerciales unificadas (llamada/email/reunion/visita/seguimiento/demo).

Entidad propia crm_actividades enlazada a lead/oportunidad/cliente que REUTILIZA la infraestructura
existente: crea una tarea (services.tareas) para el seguimiento y, para reuniones/visitas/demos, un
evento de calendario (services.calendario). No duplica logica: guarda las referencias (ref_tarea/ref_evento).
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.actividades")
TIPOS = ("llamada", "email", "reunion", "visita", "seguimiento", "demo")
_TIPOS_CALENDARIO = {"reunion", "visita", "demo"}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_actividad(tipo, asunto, *, id_lead=None, id_oportunidad=None, id_cliente=None,
                    responsable=None, vencimiento=None, notas=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    ref_tarea = ref_evento = None
    # Reutiliza tareas para el seguimiento operativo.
    try:
        from src.services import tareas
        ref_tarea = tareas.crear_tarea(f"[CRM:{tipo}] {asunto}", descripcion=notas,
                                        asignado_a=responsable, id_empresa=eid)
    except Exception as e:
        logger.debug("tareas no disponible: %s", e)
    # Reuniones/visitas/demos -> evento de calendario.
    if tipo in _TIPOS_CALENDARIO and vencimiento:
        try:
            from src.services import calendario
            ref_evento = calendario.crear_evento(f"[CRM:{tipo}] {asunto}", vencimiento, tipo=tipo,
                                                  descripcion=notas, creado_por=responsable, id_empresa=eid)
        except Exception as e:
            logger.debug("calendario no disponible: %s", e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO crm_actividades (id_empresa, tipo, asunto, id_lead, id_oportunidad, "
                        "id_cliente, responsable, vencimiento, notas, ref_tarea, ref_evento) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, tipo, asunto, id_lead, id_oportunidad, id_cliente, responsable,
                         vencimiento, notas, ref_tarea, ref_evento))
            aid = cur.lastrowid
            conn.commit()
        # Si la actividad es sobre un lead, refresca su ultimo contacto.
        if id_lead:
            try:
                from src.services.crm import leads
                leads.actualizar_lead(id_lead, fecha_ultimo_contacto=__import__("datetime").datetime.now())
            except Exception:
                pass
        log_auditoria("crm", "CRM_ACTIVITY_CREATED", "crm_actividades", f"act={aid} {tipo}")
        return aid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_actividad: %s", e)
        return None


def completar(id_actividad, *, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_actividades SET estado='completada' WHERE id=%s", (id_actividad,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("completar: %s", e)
        return False


def listar(*, id_lead=None, id_oportunidad=None, id_cliente=None, tipo=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM crm_actividades WHERE id_empresa=%s"
    p = [eid]
    for col, val in (("id_lead", id_lead), ("id_oportunidad", id_oportunidad),
                     ("id_cliente", id_cliente), ("tipo", tipo)):
        if val is not None:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []
