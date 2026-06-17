"""
Mapeo de cuentas contables (E6.4) — parametrización evento/clave → cuenta.

Resuelve la cuenta a usar para cada concepto (ventas, IVA, formas de pago, compras,
terceros…), con valores POR DEFECTO (PGC) y override por empresa en `contab_mapeo`.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("contab.mapeo")

# Valores por defecto (clave "ambito" o "ambito:clave").
DEFAULTS = {
    "venta": "700", "iva_rep": "477", "cliente": "430",
    "compra": "600", "iva_sop": "472", "proveedor": "400",
    "devolucion_venta": "708", "devolucion_compra": "608",
    "merma": "659", "existencias": "300",
    "forma_pago:efectivo": "570", "forma_pago:tarjeta": "572",
    "forma_pago:transferencia": "572", "forma_pago:factura": "430",
}


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def cuenta(ambito, clave="", id_empresa=None) -> str | None:
    """Cuenta para (ambito, clave): primero `contab_mapeo`, si no, DEFAULTS."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_cuenta FROM contab_mapeo WHERE id_empresa=%s AND ambito=%s "
                        "AND clave=%s", (id_empresa, ambito, clave or ""))
            r = cur.fetchone()
            if r:
                return r[0] if not isinstance(r, dict) else r["codigo_cuenta"]
    except Exception as e:
        logger.debug("cuenta(%s,%s): %s", ambito, clave, e)
    return DEFAULTS.get(f"{ambito}:{clave}" if clave else ambito) or DEFAULTS.get(ambito)


def set_mapeo(ambito, codigo_cuenta, clave="", id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO contab_mapeo (id_empresa, ambito, clave, codigo_cuenta) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE codigo_cuenta=VALUES(codigo_cuenta)",
                        (id_empresa, ambito, clave or "", codigo_cuenta))
            conn.commit()
        return True
    except Exception as e:
        logger.error("set_mapeo(%s): %s", ambito, e)
        return False


def cuenta_forma_pago(forma_pago, id_empresa=None) -> str:
    fp = (forma_pago or "efectivo").strip().lower()
    return cuenta("forma_pago", fp, id_empresa) or "570"
