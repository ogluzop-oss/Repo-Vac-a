"""
Histórico de ventas (`ventas_historicas`) — mirror de solo-forecasting.

Alimenta ÚNICAMENTE `predecir_ventas_semanales()`/Prophet (`gui/informe_reposicion.py`); NUNCA toca
`ventas` ni ningún dato financiero/fiscal — es intencionadamente una tabla de apoyo sin las
implicaciones de negocio (stock, contabilidad, auditoría fiscal) que sí tienen `articulos`/`clientes`/
`proveedores`. Por eso este wrapper es deliberadamente delgado: un único upsert idempotente por
(empresa, fecha, código), igual que ya hacía `services/importacion/motor.py` en crudo — se extrae aquí
SOLO para que la importación rutee por la capa de dominio (`db/*`) como el resto de entidades, no
porque el propio dato lo necesite (no dispara eventos ni auditoría: no representa una venta real).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("ventas_historicas.db")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


def registrar_venta_historica(fecha, codigo, *, cantidad=0, importe=0, id_empresa=None) -> bool:
    """Upsert idempotente de UNA fila de histórico: (id_empresa, fecha, codigo_articulo) es la clave
    de deduplicación — reimportar el mismo origen ACTUALIZA cantidad/importe, no duplica filas."""
    if not fecha or not codigo:
        return False
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ventas_historicas (id_empresa, fecha, codigo_articulo, cantidad, importe) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad), "
                "importe=VALUES(importe)",
                (id_empresa, fecha, str(codigo), cantidad or 0, importe or 0))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_venta_historica(%s,%s): %s", fecha, codigo, e)
        return False
