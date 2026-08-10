"""
Communication Timeline (CCP Fase II · B4) — cronología ÚNICA de comunicaciones.

Une TODA la relación con un contacto/organización en un solo historial, sin separar por canal:
comunicaciones salientes (`ccp_comunicaciones`, cualquier canal) + correos entrantes
(`correos_recibidos`). Puede verse plano (cronológico) o agrupado por Conversation. Multiempresa.
API-First (sin PyQt).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.timeline")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def timeline(id_empresa=None, *, correo=None, limite=200) -> list:
    """Lista unificada de eventos de comunicación (salientes + entrantes) ordenada por fecha desc.
    Cada evento: {sentido, canal, fecha, asunto, contraparte, com_id, estado, conversation_id}."""
    id_empresa = _emp(id_empresa)
    if not id_empresa:
        return []
    correo_n = correo.strip().lower() if correo else None
    eventos = []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Salientes (cualquier canal).
            q = ("SELECT com_id, canal, creado AS fecha, asunto, destinatario AS contraparte, estado, "
                 "conversation_id FROM ccp_comunicaciones WHERE id_empresa=%s")
            p = [id_empresa]
            if correo_n:
                q += " AND LOWER(destinatario)=%s"; p.append(correo_n)
            q += " ORDER BY id DESC LIMIT %s"; p.append(int(limite))
            cur.execute(q, p)
            for r in _filas_a_dicts(cur, cur.fetchall()):
                r["sentido"] = "saliente"; eventos.append(r)
            # Entrantes (correo recibido).
            try:
                q2 = ("SELECT NULL AS com_id, 'email' AS canal, fecha, asunto, remitente AS contraparte,"
                      " 'recibido' AS estado, NULL AS conversation_id FROM correos_recibidos "
                      "WHERE id_empresa=%s")
                p2 = [id_empresa]
                if correo_n:
                    q2 += " AND LOWER(remitente) LIKE %s"; p2.append(f"%{correo_n}%")
                q2 += " ORDER BY id DESC LIMIT %s"; p2.append(int(limite))
                cur.execute(q2, p2)
                for r in _filas_a_dicts(cur, cur.fetchall()):
                    r["sentido"] = "entrante"; eventos.append(r)
            except Exception as e:
                logger.debug("timeline entrantes: %s", e)
    except Exception as e:
        logger.debug("timeline: %s", e)
        return []
    eventos.sort(key=lambda e: (str(e.get("fecha") or ""), ), reverse=True)
    return eventos[:int(limite)]


def timeline_agrupado(id_empresa=None, *, correo=None, limite=200) -> list:
    """Timeline agrupado por Conversation (hilo). Devuelve [{conversation_id, eventos:[...]}]."""
    eventos = timeline(id_empresa, correo=correo, limite=limite)
    grupos: dict = {}
    orden = []
    for e in eventos:
        cid = e.get("conversation_id") or f"_sin_hilo_{e.get('contraparte')}"
        if cid not in grupos:
            grupos[cid] = []; orden.append(cid)
        grupos[cid].append(e)
    return [{"conversation_id": (cid if not str(cid).startswith("_sin_hilo_") else None),
             "eventos": grupos[cid]} for cid in orden]
