"""
Registro de eventos de WEBHOOK de pago (Fase 3) — idempotencia y trazabilidad.

`reclamar_evento` inserta el evento de forma atómica (UNIQUE empresa+proveedor+
evento): si ya existía, devuelve None → el evento es un DUPLICADO/replay y no se
reprocesa. Tras procesarlo, `actualizar_evento` guarda el resultado. Por empresa.
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, ensure_schema,
                             obtener_conexion)

logger = logging.getLogger("pagos_webhooks_db")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def reclamar_evento(proveedor, evento_id, evento_tipo=None, referencia=None,
                    ip_origen=None, id_empresa=None):
    """Reserva el evento (anti-duplicado). Devuelve el id de log si es NUEVO,
    o None si ya estaba registrado (replay/duplicado)."""
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO pagos_webhooks_log "
                "(id_empresa, proveedor, evento_id, evento_tipo, referencia, ip_origen, resultado) "
                "VALUES (%s,%s,%s,%s,%s,%s,'recibido')",
                (id_empresa, proveedor, evento_id, evento_tipo, referencia, ip_origen))
            conn.commit()
            if cur.rowcount == 0:
                return None          # ya existía → duplicado
            return cur.lastrowid
    except Exception as e:
        logger.error("reclamar_evento(%s/%s): %s", proveedor, evento_id, e)
        return None


def actualizar_evento(id_log, id_pedido=None, estado=None, resultado=None,
                      referencia=None, evento_tipo=None) -> bool:
    sets, params = [], []
    for col, val in (("id_pedido", id_pedido), ("estado", estado),
                     ("resultado", resultado), ("referencia", referencia),
                     ("evento_tipo", evento_tipo)):
        if val is not None:
            sets.append(f"{col}=%s"); params.append(val)
    if not sets:
        return True
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pagos_webhooks_log SET {', '.join(sets)} WHERE id=%s",
                        (*params, id_log))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_evento(%s): %s", id_log, e)
        return False


def listar_eventos(id_pedido=None, proveedor=None, id_empresa=None, limite=200) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_pedido:
        filtros.append("id_pedido=%s"); params.append(id_pedido)
    if proveedor:
        filtros.append("proveedor=%s"); params.append(proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM pagos_webhooks_log WHERE " + " AND ".join(filtros)
                        + " ORDER BY recibido DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_eventos: %s", e)
        return []
