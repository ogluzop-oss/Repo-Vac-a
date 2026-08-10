"""
Conversaciones (CCP Fase II · B4) — hilos que agrupan comunicaciones relacionadas.

Una Conversation agrupa múltiples comunicaciones (de cualquier canal) con un mismo contacto/entidad
bajo un único hilo. El Communication Service asigna cada comunicación a su conversación (crea o
continúa). Multiempresa. API-First (sin PyQt).
"""

import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.conversaciones")

_VENTANA_DIAS = 30   # dentro de esta ventana se continúa el hilo abierto del mismo contacto


def obtener_o_crear(id_empresa, *, correo, asunto=None, canal=None, entidad_tipo=None,
                    entidad_id=None) -> int | None:
    """Devuelve el id de conversación: continúa el hilo ABIERTO más reciente del contacto (dentro de
    la ventana) o crea uno nuevo. Actualiza contador/canales/fecha."""
    if not id_empresa or not correo:
        return None
    correo = correo.strip().lower()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, canales FROM ccp_conversaciones WHERE id_empresa=%s AND correo=%s AND "
                "estado='abierta' AND (actualizado IS NULL OR actualizado >= (NOW() - INTERVAL %s DAY)"
                " OR creado >= (NOW() - INTERVAL %s DAY)) ORDER BY id DESC LIMIT 1",
                (id_empresa, correo, _VENTANA_DIAS, _VENTANA_DIAS))
            row = _fila_a_dict(cur, cur.fetchone())
            if row:
                cid = row["id"]
                canales = set((row.get("canales") or "").split(",")) - {""}
                if canal:
                    canales.add(canal)
                cur.execute("UPDATE ccp_conversaciones SET n_mensajes=n_mensajes+1, canales=%s, "
                            "actualizado=NOW() WHERE id=%s", (",".join(sorted(canales)), cid))
            else:
                cur.execute(
                    "INSERT INTO ccp_conversaciones (id_empresa, entidad_tipo, entidad_id, correo, "
                    "asunto, canales, estado, n_mensajes) VALUES (%s,%s,%s,%s,%s,%s,'abierta',1)",
                    (id_empresa, entidad_tipo, entidad_id, correo, asunto, canal or ""))
                cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.debug("obtener_o_crear conversación: %s", e)
        return None


def listar_conversaciones(id_empresa=None, *, correo=None, limite=100) -> list:
    from src.db.empresa import empresa_actual_id
    id_empresa = id_empresa or empresa_actual_id()
    q = "SELECT * FROM ccp_conversaciones WHERE id_empresa=%s"
    p = [id_empresa]
    if correo:
        q += " AND correo=%s"; p.append(correo.strip().lower())
    q += " ORDER BY actualizado DESC, id DESC LIMIT %s"; p.append(int(limite))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_conversaciones: %s", e)
        return []


def mensajes(conversation_id) -> list:
    """Comunicaciones (de cualquier canal) que pertenecen a una conversación."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ccp_comunicaciones WHERE conversation_id=%s ORDER BY id",
                        (conversation_id,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("mensajes(%s): %s", conversation_id, e)
        return []


def cerrar(conversation_id) -> bool:
    return _set_estado(conversation_id, "cerrada")


def reabrir(conversation_id) -> bool:
    return _set_estado(conversation_id, "abierta")


def _set_estado(conversation_id, estado) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ccp_conversaciones SET estado=%s, actualizado=NOW() WHERE id=%s",
                        (estado, conversation_id))
            conn.commit()
            return True
    except Exception as e:
        logger.debug("_set_estado(%s): %s", conversation_id, e)
        return False
