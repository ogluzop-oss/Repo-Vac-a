"""
CRM-C — Oportunidades. Valor, probabilidad, etapa, responsable, cierre. Integra con BI (forecast).
Mover de etapa actualiza probabilidad; cerrar ganado/perdido registra auditoria. Multiempresa.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.oportunidades")
ESTADOS = ("abierta", "ganada", "perdida")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.1): la resolución de empresa pasa por la capa de identidad (Strangler).
    from src.services.crm.identidad_crm import empresa_id
    return empresa_id(id_empresa)


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_oportunidad(titulo, *, valor=0, id_lead=None, id_cliente=None, etapa_codigo="lead",
                      responsable=None, fecha_cierre_prevista=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    from src.services.crm import pipeline
    pid = pipeline.asegurar_pipeline_defecto(id_empresa=eid)
    etapa = pipeline.etapa_por_codigo(etapa_codigo, id_empresa=eid) or {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO crm_oportunidades (id_empresa, titulo, id_pipeline, id_etapa, id_lead, "
                        "id_cliente, valor, probabilidad, responsable, fecha_cierre_prevista) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, titulo, pid, etapa.get("id"), id_lead, id_cliente, valor,
                         etapa.get("probabilidad", 0), responsable, fecha_cierre_prevista))
            oid = cur.lastrowid
            conn.commit()
        log_auditoria("crm", "CRM_OPPORTUNITY_CREATED", "crm_oportunidades", f"op={oid} valor={valor}")
        return oid
    except Exception as e:
        logger.error("crear_oportunidad: %s", e)
        return None


def mover_etapa(id_oportunidad, etapa_codigo, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    from src.services.crm import pipeline
    etapa = pipeline.etapa_por_codigo(etapa_codigo, id_empresa=eid)
    if not etapa:
        return {"ok": False, "error": "etapa inexistente"}
    estado, cierre = "abierta", None
    accion = None
    if etapa.get("es_ganado"):
        estado, cierre, accion = "ganada", _dt.datetime.now(), "CRM_OPPORTUNITY_WON"
    elif etapa.get("es_perdido"):
        estado, cierre, accion = "perdida", _dt.datetime.now(), "CRM_OPPORTUNITY_LOST"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_oportunidades SET id_etapa=%s, probabilidad=%s, estado=%s, "
                        "fecha_cierre=%s WHERE id=%s AND id_empresa=%s",
                        (etapa["id"], etapa.get("probabilidad", 0), estado, cierre, id_oportunidad, eid))
            conn.commit()
        if accion:
            log_auditoria("crm", accion, "crm_oportunidades", f"op={id_oportunidad}")
        return {"ok": True, "estado": estado, "probabilidad": etapa.get("probabilidad", 0)}
    except Exception as e:
        logger.error("mover_etapa: %s", e)
        return {"ok": False, "error": str(e)}


def cerrar(id_oportunidad, ganada=True, *, motivo=None, id_empresa=None) -> dict:
    return mover_etapa(id_oportunidad, "ganado" if ganada else "perdido", id_empresa=id_empresa)


def listar(*, estado=None, responsable=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM crm_oportunidades WHERE id_empresa=%s"
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
        logger.error("listar: %s", e)
        return []


def valor_pipeline(*, id_empresa=None) -> dict:
    """Valor total y ponderado (valor*probabilidad) del pipeline abierto = forecast comercial."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(valor),0), COALESCE(SUM(valor*probabilidad/100),0), COUNT(*) "
                        "FROM crm_oportunidades WHERE id_empresa=%s AND estado='abierta'", (eid,))
            r = cur.fetchone()
            r = list(r.values()) if isinstance(r, dict) else r
            return {"valor_total": float(r[0]), "valor_ponderado": round(float(r[1]), 2), "abiertas": int(r[2])}
    except Exception as e:
        logger.error("valor_pipeline: %s", e)
        return {"valor_total": 0, "valor_ponderado": 0, "abiertas": 0}


def vincular_venta(id_oportunidad, id_venta, *, id_empresa=None) -> dict:
    """Vincula una oportunidad con la VENTA/pedido generado (pedidos vinculados, Módulo 1). Reutiliza
    la venta existente (no la crea); marca la oportunidad como ganada si aún estaba abierta. Auditado."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_oportunidades SET id_venta=%s, "
                        "estado=CASE WHEN estado='abierta' THEN 'ganada' ELSE estado END, "
                        "fecha_cierre=CASE WHEN estado='abierta' THEN NOW() ELSE fecha_cierre END "
                        "WHERE id=%s AND id_empresa<=>%s", (id_venta, id_oportunidad, eid))
            conn.commit()
        log_auditoria("crm", "OPORTUNIDAD_VINCULADA_VENTA", "crm_oportunidades",
                      f"op={id_oportunidad}->venta={id_venta}")
        try:
            from src.services import eventos
            eventos.publicar("crm.oportunidad_vinculada", ref_entidad="crm_oportunidades",
                             ref_id=id_oportunidad, id_empresa=eid,
                             payload={"id_oportunidad": id_oportunidad, "id_venta": id_venta})
        except Exception:
            pass
        return {"ok": True, "id_oportunidad": id_oportunidad, "id_venta": id_venta}
    except Exception as e:
        logger.error("vincular_venta: %s", e)
        return {"ok": False, "motivo": str(e)}


def ventas_de_oportunidad(id_oportunidad):
    """Devuelve la venta vinculada a una oportunidad (o None)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_venta FROM crm_oportunidades WHERE id=%s", (id_oportunidad,))
            r = cur.fetchone()
            v = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            return v
    except Exception:
        return None
