"""
Configuración del % de DESCUENTO DE PERSONAL (empleados) por empresa.

Lo usa el TPV en la "Compra personal" (aplica este % a toda la compra tras validar el PIN del empleado)
y la opción "Editar % descuento personal" (solo admin/superadmin). Multiempresa (clave por id_empresa).
Ver migración 0159. Degradable: si la tabla no existe aún, devuelve el valor por defecto.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("descuentos_db")

DESCUENTO_PERSONAL_DEFECTO = 10.0


def _empresa(id_empresa=None):
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def obtener_descuento_personal(id_empresa=None) -> float:
    """% de descuento de personal de la empresa (por defecto 10%)."""
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT descuento_personal_pct FROM config_descuentos WHERE id_empresa=%s",
                        (id_empresa,))
            r = cur.fetchone()
            if r and r[0] is not None:
                return float(r[0])
    except Exception as e:
        logger.error("obtener_descuento_personal: %s", e)
    return DESCUENTO_PERSONAL_DEFECTO


def guardar_descuento_personal(pct, id_empresa=None) -> bool:
    """Fija el % de descuento de personal (0–100). Solo debería invocarse tras validar admin/superadmin."""
    id_empresa = _empresa(id_empresa)
    try:
        pct = float(str(pct).replace(",", "."))
    except Exception:
        return False
    if pct < 0 or pct > 100:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO config_descuentos (id_empresa, descuento_personal_pct) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE descuento_personal_pct=VALUES(descuento_personal_pct)",
                (id_empresa, pct))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_descuento_personal: %s", e)
        return False
