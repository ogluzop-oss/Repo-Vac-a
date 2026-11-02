"""
Configuración de Facturación por empresa. Hoy: umbral de morosidad tolerado sobre los PROPIOS
clientes de la empresa (facturas impagadas/vencidas en `facturas_cliente`) — cada empresa que contrata
Smart Manager decide su propia tolerancia, ya que el riesgo de impago aceptable varía por sector/
tamaño. Sin relación con la suscripción de esa empresa a Smart Manager (esa caducidad se avisa por otro
sistema, en el menú principal). Mismo patrón que `services/compras/b2b_presupuesto.py` (tabla propia
mínima, valor por defecto si la empresa no lo ha configurado todavía).
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("facturacion.config")

MOROSIDAD_TOLERADA_DEFECTO = 15.0


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def obtener_morosidad_tolerada(id_empresa) -> float:
    """% de morosidad tolerado antes de que el Gemelo Financiero levante alerta de riesgo. 15% por
    defecto si la empresa no lo ha configurado todavía (nunca None: siempre hay un umbral con el que
    comparar)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT morosidad_tolerada_pct FROM facturacion_config WHERE id_empresa=%s",
                        (id_empresa,))
            row = cur.fetchone()
            if not row:
                return MOROSIDAD_TOLERADA_DEFECTO
            v = _fila(cur, row)["morosidad_tolerada_pct"]
            return float(v) if v is not None else MOROSIDAD_TOLERADA_DEFECTO
    except Exception as e:
        logger.error("obtener_morosidad_tolerada(%s): %s", id_empresa, e)
        return MOROSIDAD_TOLERADA_DEFECTO


def guardar_morosidad_tolerada(id_empresa, valor) -> bool:
    try:
        valor_f = float(valor)
        if not (0 <= valor_f <= 100):
            return False
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO facturacion_config (id_empresa, morosidad_tolerada_pct) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE morosidad_tolerada_pct=VALUES(morosidad_tolerada_pct)",
                (id_empresa, valor_f))
            conn.commit()
        return True
    except (TypeError, ValueError):
        return False
    except Exception as e:
        logger.error("guardar_morosidad_tolerada(%s): %s", id_empresa, e)
        return False
