"""
Límite de gasto mensual B2B por empresa (Smart Suppliers B2B · Fase 3). Tabla propia
(`b2b_empresa_config`), distinta de `services.finanzas.presupuestos` (presupuestos contables por
ejercicio — concepto distinto). El "gasto validado del mes" solo cuenta pedidos B2B que ya avanzaron
más allá de BORRADOR/CANCELADA (b2b_pedidos.tramitar los deja en CONFIRMADA como mínimo).
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_presupuesto")

# Estados de transaccion_comercial que cuentan como gasto real (excluye BORRADOR/CANCELADA/DEVUELTA/
# ABONADA/EXPIRADA — ver services.comercio_digital.transacciones.ESTADOS).
_ESTADOS_VALIDADOS = ("CONFIRMADA", "PAGADA", "PREPARANDO", "ENVIADA", "ENTREGADA", "FACTURADA")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def obtener_limite(id_empresa) -> float | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT presupuesto_mensual FROM b2b_empresa_config WHERE id_empresa=%s",
                        (id_empresa,))
            row = cur.fetchone()
            if not row:
                return None
            v = _fila(cur, row)["presupuesto_mensual"]
            return float(v) if v is not None else None
    except Exception as e:
        logger.error("obtener_limite(%s): %s", id_empresa, e)
        return None


def guardar_limite(id_empresa, limite) -> bool:
    try:
        limite_f = float(limite) if str(limite).strip() != "" else None
        if limite_f is not None and limite_f < 0:
            return False
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_empresa_config (id_empresa, presupuesto_mensual) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE presupuesto_mensual=VALUES(presupuesto_mensual)",
                (id_empresa, limite_f))
            conn.commit()
        return True
    except (TypeError, ValueError):
        return False
    except Exception as e:
        logger.error("guardar_limite(%s): %s", id_empresa, e)
        return False


def gasto_validado_mes(id_empresa) -> float:
    """Suma de `total` de transacciones B2B de la empresa, ya validadas (no BORRADOR/CANCELADA/
    DEVUELTA/ABONADA/EXPIRADA), creadas en el mes en curso."""
    try:
        ensure_schema()
        placeholders = ",".join(["%s"] * len(_ESTADOS_VALIDADOS))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(SUM(total),0) FROM transaccion_comercial WHERE id_empresa=%s "
                f"AND origen='b2b' AND estado IN ({placeholders}) "
                f"AND YEAR(creada)=YEAR(CURDATE()) AND MONTH(creada)=MONTH(CURDATE())",
                (id_empresa, *_ESTADOS_VALIDADOS))
            row = cur.fetchone()
            v = row[0] if not isinstance(row, dict) else list(row.values())[0]
            return float(v or 0)
    except Exception as e:
        logger.error("gasto_validado_mes(%s): %s", id_empresa, e)
        return 0.0


def resumen_presupuesto(id_empresa, total_carrito: float = 0.0) -> dict:
    """{limite, gasto_mes, total_carrito, proyectado, pct, excedido}. `pct`/`excedido` son None si no
    hay límite configurado (nada que comparar — no se finge un 0% falso)."""
    limite = obtener_limite(id_empresa)
    gasto_mes = gasto_validado_mes(id_empresa)
    proyectado = round(gasto_mes + float(total_carrito or 0), 2)
    pct = None
    excedido = False
    if limite:
        pct = round(min(proyectado / limite * 100, 999), 1)
        excedido = proyectado > limite
    return {"limite": limite, "gasto_mes": round(gasto_mes, 2), "total_carrito": round(float(total_carrito or 0), 2),
            "proyectado": proyectado, "pct": pct, "excedido": excedido}
