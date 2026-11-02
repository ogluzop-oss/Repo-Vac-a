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

_SIN_CAMBIO = object()  # sentinel: distingue "no tocar este campo" de "ponlo a None"

_DEFECTOS = {
    "texto_legal": "",
    "mensaje_despedida": "¡Gracias por su compra!",
    "devol_dias": 30,
    # NULL = desactivado (nunca bloquea devoluciones por descuento). Ver "Artículos con
    # descuento" en Configuración → Plazo devolución.
    "descuento_min_bloqueo": None,
}


def obtener_config_ticket(id_empresa=None) -> dict:
    """Devuelve {texto_legal, mensaje_despedida, devol_dias, descuento_min_bloqueo} de la empresa."""
    id_empresa = id_empresa or empresa_actual_id()
    datos = dict(_DEFECTOS)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT texto_legal, mensaje_despedida, devol_dias, descuento_min_bloqueo "
                "FROM config_ticket WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            if row:
                if isinstance(row, dict):
                    tl, md, dd = row.get("texto_legal"), row.get("mensaje_despedida"), row.get("devol_dias")
                    dmb = row.get("descuento_min_bloqueo")
                else:
                    tl, md, dd = row[0], row[1], row[2]
                    dmb = row[3] if len(row) > 3 else None
                if tl is not None:
                    datos["texto_legal"] = tl
                if md:
                    datos["mensaje_despedida"] = md
                if dd is not None:
                    datos["devol_dias"] = int(dd)
                if dmb is not None:
                    datos["descuento_min_bloqueo"] = float(dmb)
    except Exception as e:
        logger.error("Error obtener_config_ticket: %s", e)
    return datos


def calcular_fecha_limite_devolucion(fecha_venta, id_empresa=None):
    """Fecha límite de devolución CONGELADA para una venta: `fecha_venta` + el plazo (días)
    VIGENTE en este preciso momento. Se llama una única vez, al registrar la venta — el
    resultado se persiste en `ventas.fecha_limite_devolucion` para que no cambie después
    aunque la empresa modifique su plazo más adelante (ver migr. 0232)."""
    from datetime import timedelta
    dias = obtener_config_ticket(id_empresa)["devol_dias"]
    return fecha_venta + timedelta(days=int(dias))


def guardar_config_ticket(texto_legal=None, mensaje_despedida=None,
                          devol_dias=None, id_empresa=None, *,
                          descuento_min_bloqueo=_SIN_CAMBIO) -> bool:
    """Upsert de la configuración del ticket de la empresa.

    `descuento_min_bloqueo`: usa el sentinel `_SIN_CAMBIO` (no el `None` por defecto de los demás
    parámetros) porque aquí `None` es un valor VÁLIDO y distinto de "no tocar" — pasar
    `descuento_min_bloqueo=None` explícitamente DESACTIVA el bloqueo por descuento."""
    id_empresa = id_empresa or empresa_actual_id()
    actual = obtener_config_ticket(id_empresa)
    tl = actual["texto_legal"] if texto_legal is None else texto_legal
    md = actual["mensaje_despedida"] if mensaje_despedida is None else mensaje_despedida
    dd = actual["devol_dias"] if devol_dias is None else int(devol_dias)
    dmb = actual["descuento_min_bloqueo"] if descuento_min_bloqueo is _SIN_CAMBIO \
        else descuento_min_bloqueo
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO config_ticket (id_empresa, texto_legal, mensaje_despedida, devol_dias, "
                "descuento_min_bloqueo) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "texto_legal=VALUES(texto_legal), mensaje_despedida=VALUES(mensaje_despedida), "
                "devol_dias=VALUES(devol_dias), descuento_min_bloqueo=VALUES(descuento_min_bloqueo)",
                (id_empresa, tl, md, dd, dmb))
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error guardar_config_ticket: %s", e)
        return False
