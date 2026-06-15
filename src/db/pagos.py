"""
Configuración de la PASARELA DE PAGO por empresa (cobro online real).

Guarda el proveedor activo (stripe/paypal/redsys/simulado), las credenciales, el
comercio, el modo (test/live) y la moneda. El servicio de cobro usa esta config
para elegir la pasarela. Multiempresa (PK id_empresa). Las credenciales nunca se
muestran completas en la UI. Ver [[project_venta_online]].
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("pagos_db")

PROVEEDORES = ("simulado", "stripe", "paypal", "redsys")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def obtener_config(id_empresa=None) -> dict:
    """Config de la pasarela de la empresa (dict con defaults si no existe fila)."""
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "proveedor": "simulado", "api_key": "",
            "api_secret": "", "comercio": "", "modo": "test", "moneda": "EUR",
            "estado": "activo"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM pasarela_config WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if r:
                if not isinstance(r, dict):
                    r = dict(zip([d[0] for d in cur.description], r))
                base.update({k: (r.get(k) if r.get(k) is not None else base[k]) for k in base})
    except Exception as e:
        logger.error("obtener_config: %s", e)
    return base


def guardar_config(proveedor=None, api_key=None, api_secret=None, comercio=None,
                   modo=None, moneda=None, estado=None, id_empresa=None) -> bool:
    """Crea/actualiza (upsert) la config de pasarela. Solo cambia lo indicado."""
    id_empresa = _empresa(id_empresa)
    actual = obtener_config(id_empresa)
    nueva = {
        "proveedor": (proveedor or actual["proveedor"]),
        "api_key": (api_key if api_key is not None else actual["api_key"]),
        "api_secret": (api_secret if api_secret is not None else actual["api_secret"]),
        "comercio": (comercio if comercio is not None else actual["comercio"]),
        "modo": (modo or actual["modo"]),
        "moneda": (moneda or actual["moneda"]),
        "estado": (estado or actual["estado"]),
    }
    if nueva["proveedor"] not in PROVEEDORES:
        nueva["proveedor"] = "simulado"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pasarela_config "
                "(id_empresa, proveedor, api_key, api_secret, comercio, modo, moneda, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE proveedor=VALUES(proveedor), "
                "api_key=VALUES(api_key), api_secret=VALUES(api_secret), "
                "comercio=VALUES(comercio), modo=VALUES(modo), moneda=VALUES(moneda), "
                "estado=VALUES(estado)",
                (id_empresa, nueva["proveedor"], nueva["api_key"], nueva["api_secret"],
                 nueva["comercio"], nueva["modo"], nueva["moneda"], nueva["estado"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False
