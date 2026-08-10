"""
Timeline Builder (Fase III · B6) — une TODAS las fuentes en una cronología única (solo lectura).

Fuentes: eventos (Event Bus), comunicaciones (ccp_comunicaciones/Communication ID), timeline CCP,
conversación y auditoría. No modifica nada. Multiempresa.
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("audit_replay.timeline")


def _item(fuente, fecha, tipo, detalle, actor=None, ref=None):
    return {"fuente": fuente, "fecha": str(fecha or ""), "tipo": tipo, "detalle": detalle,
            "actor": actor, "ref": ref}


def construir(id_empresa, *, com_id=None, correo=None, ref_entidad=None, ref_id=None,
              limite=500) -> list:
    """Devuelve la lista unificada de sucesos (orden cronológico ascendente)."""
    items = []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Comunicaciones (por com_id, correo o empresa).
            q = "SELECT * FROM ccp_comunicaciones WHERE id_empresa=%s"
            p = [id_empresa]
            if com_id:
                q += " AND com_id=%s"; p.append(com_id)
            elif correo:
                q += " AND LOWER(destinatario)=%s"; p.append(correo.lower())
            q += " ORDER BY id LIMIT %s"; p.append(int(limite))
            cur.execute(q, p)
            for c in _filas_a_dicts(cur, cur.fetchall()):
                items.append(_item("comunicacion", c.get("creado"), c.get("estado"),
                                   f"{c.get('canal')} → {c.get('destinatario')}: {c.get('asunto')}",
                                   actor=c.get("usuario"), ref=c.get("com_id")))
    except Exception as e:
        logger.debug("construir comunicaciones: %s", e)
    # Eventos (Event Bus).
    try:
        from src.services import eventbus
        for e in eventbus.replay(id_empresa=id_empresa, ref_entidad=ref_entidad, ref_id=ref_id,
                                 limite=limite):
            items.append(_item("evento", e.get("creado") or e.get("created_at"), e.get("tipo"),
                               f"evento {e.get('tipo')} ({e.get('estado')})", actor=e.get("usuario"),
                               ref=e.get("ref_id")))
    except Exception as e:
        logger.debug("construir eventos: %s", e)
    items.sort(key=lambda x: x["fecha"])
    return items
