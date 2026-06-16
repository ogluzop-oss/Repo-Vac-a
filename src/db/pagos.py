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

# Proveedor recomendado por defecto para el mercado principal (España).
PROVEEDOR_DEFECTO = "redsys"
# Lista de referencia (la fuente real es el registro de pasarelas; aquí no se usa
# como filtro para no impedir añadir pasarelas nuevas sin tocar el núcleo).
PROVEEDORES = ("redsys", "stripe", "paypal", "simulado")

# Campos sensibles cifrados en reposo (Fernet, ver src/utils/cripto.py).
_SECRETOS = ("api_key", "api_secret", "webhook_secret")


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
    base = {"id_empresa": id_empresa, "proveedor": PROVEEDOR_DEFECTO, "api_key": "",
            "api_secret": "", "comercio": "", "modo": "test", "moneda": "EUR",
            "webhook_secret": "", "estado": "activo"}
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
    # Descifra los secretos en reposo (retrocompatible con valores en claro).
    from src.utils import cripto
    for k in _SECRETOS:
        base[k] = cripto.descifrar_seguro(base.get(k)) or ""
    return base


def guardar_config(proveedor=None, api_key=None, api_secret=None, comercio=None,
                   modo=None, moneda=None, estado=None, webhook_secret=None,
                   id_empresa=None) -> bool:
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
        "webhook_secret": (webhook_secret if webhook_secret is not None else actual["webhook_secret"]),
        "estado": (estado or actual["estado"]),
    }
    # Se acepta cualquier proveedor registrado (no se filtra contra una lista fija,
    # para permitir añadir pasarelas nuevas sin tocar el núcleo). Solo se exige valor.
    if not nueva["proveedor"]:
        nueva["proveedor"] = PROVEEDOR_DEFECTO
    from src.utils import cripto
    def _cif(v):
        return cripto.cifrar(v) if v else v
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pasarela_config "
                "(id_empresa, proveedor, api_key, api_secret, comercio, modo, moneda, "
                " webhook_secret, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE proveedor=VALUES(proveedor), "
                "api_key=VALUES(api_key), api_secret=VALUES(api_secret), "
                "comercio=VALUES(comercio), modo=VALUES(modo), moneda=VALUES(moneda), "
                "webhook_secret=VALUES(webhook_secret), estado=VALUES(estado)",
                (id_empresa, nueva["proveedor"], _cif(nueva["api_key"]), _cif(nueva["api_secret"]),
                 nueva["comercio"], nueva["modo"], nueva["moneda"],
                 _cif(nueva["webhook_secret"]), nueva["estado"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False


def migrar_cifrado():
    """Cifra en reposo los secretos que aún estuvieran en claro (idempotente)."""
    from src.utils import cripto
    if not cripto.cifrado_disponible():
        return
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_empresa, api_key, api_secret, webhook_secret FROM pasarela_config")
        filas = cur.fetchall()
        for row in filas:
            d = row if isinstance(row, dict) else dict(zip(
                ["id_empresa", "api_key", "api_secret", "webhook_secret"], row))
            cambios = {k: cripto.cifrar(d[k]) for k in _SECRETOS
                       if d.get(k) and not cripto.parece_cifrado(d[k])}
            if cambios:
                sets = ", ".join(f"{k}=%s" for k in cambios)
                cur.execute(f"UPDATE pasarela_config SET {sets} WHERE id_empresa=%s",
                            (*cambios.values(), d["id_empresa"]))
        conn.commit()
