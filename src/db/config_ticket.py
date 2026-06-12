"""
Configuración del TICKET de compra por empresa (multi-tenant).

Fuente única para el generador de tickets del TPV: texto legal del pie,
mensaje de despedida y plazo de devolución (en días). Se persiste en la tabla
`config_ticket` (una fila por empresa). Degradación elegante con valores por
defecto razonables si no hay fila o falla la BD. Ver [[project_multitenant]].
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("config_ticket_db")

_DEFECTOS = {
    "texto_legal": "",
    "mensaje_despedida": "¡Gracias por su compra!",
    "devol_dias": 30,
}


def obtener_config_ticket(id_empresa=None) -> dict:
    """Devuelve {texto_legal, mensaje_despedida, devol_dias} de la empresa."""
    id_empresa = id_empresa or empresa_actual_id()
    datos = dict(_DEFECTOS)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT texto_legal, mensaje_despedida, devol_dias "
                "FROM config_ticket WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            if row:
                if isinstance(row, dict):
                    tl, md, dd = row.get("texto_legal"), row.get("mensaje_despedida"), row.get("devol_dias")
                else:
                    tl, md, dd = row[0], row[1], row[2]
                if tl is not None:
                    datos["texto_legal"] = tl
                if md:
                    datos["mensaje_despedida"] = md
                if dd is not None:
                    datos["devol_dias"] = int(dd)
    except Exception as e:
        logger.error("Error obtener_config_ticket: %s", e)
    return datos


def guardar_config_ticket(texto_legal=None, mensaje_despedida=None,
                          devol_dias=None, id_empresa=None) -> bool:
    """Upsert de la configuración del ticket de la empresa."""
    id_empresa = id_empresa or empresa_actual_id()
    actual = obtener_config_ticket(id_empresa)
    tl = actual["texto_legal"] if texto_legal is None else texto_legal
    md = actual["mensaje_despedida"] if mensaje_despedida is None else mensaje_despedida
    dd = actual["devol_dias"] if devol_dias is None else int(devol_dias)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO config_ticket (id_empresa, texto_legal, mensaje_despedida, devol_dias) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "texto_legal=VALUES(texto_legal), mensaje_despedida=VALUES(mensaje_despedida), "
                "devol_dias=VALUES(devol_dias)",
                (id_empresa, tl, md, dd))
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error guardar_config_ticket: %s", e)
        return False
