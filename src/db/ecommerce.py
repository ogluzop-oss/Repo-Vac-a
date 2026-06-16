"""
Configuración de e-commerce por empresa (F2 — adaptador multiplataforma).

Guarda la plataforma activa (web/woocommerce/shopify/prestashop), la URL base y
las credenciales de API. El servicio de pedidos online usa esta config para
elegir el adaptador y para el botón "Ir a la Web". Multiempresa (PK id_empresa).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("ecommerce_db")

PLATAFORMAS = ("web", "woocommerce", "shopify", "prestashop")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def obtener_config(id_empresa=None) -> dict:
    """Config de e-commerce de la empresa (dict con defaults si no existe fila)."""
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "plataforma": "web", "base_url": "",
            "api_key": "", "api_secret": "", "estado": "activo"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ecommerce_config WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if r:
                if not isinstance(r, dict):
                    r = dict(zip([d[0] for d in cur.description], r))
                base.update({k: (r.get(k) if r.get(k) is not None else base[k]) for k in base})
    except Exception as e:
        logger.error("obtener_config: %s", e)
    # Descifra los secretos en reposo (retrocompatible con valores en claro).
    from src.utils import cripto
    for k in ("api_key", "api_secret"):
        base[k] = cripto.descifrar_seguro(base.get(k)) or ""
    return base


def guardar_config(plataforma=None, base_url=None, api_key=None, api_secret=None,
                   estado=None, id_empresa=None) -> bool:
    """Crea/actualiza la config (upsert) de la empresa. Solo cambia lo indicado."""
    id_empresa = _empresa(id_empresa)
    actual = obtener_config(id_empresa)
    nueva = {
        "plataforma": (plataforma or actual["plataforma"]),
        "base_url": (base_url if base_url is not None else actual["base_url"]),
        "api_key": (api_key if api_key is not None else actual["api_key"]),
        "api_secret": (api_secret if api_secret is not None else actual["api_secret"]),
        "estado": (estado or actual["estado"]),
    }
    if nueva["plataforma"] not in PLATAFORMAS:
        nueva["plataforma"] = "web"
    from src.utils import cripto
    def _cif(v):
        return cripto.cifrar(v) if v else v
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ecommerce_config "
                "(id_empresa, plataforma, base_url, api_key, api_secret, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE plataforma=VALUES(plataforma), "
                "base_url=VALUES(base_url), api_key=VALUES(api_key), "
                "api_secret=VALUES(api_secret), estado=VALUES(estado)",
                (id_empresa, nueva["plataforma"], nueva["base_url"], _cif(nueva["api_key"]),
                 _cif(nueva["api_secret"]), nueva["estado"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False


def migrar_cifrado():
    """Cifra en reposo los secretos (api_key/api_secret) que aún estuvieran en
    claro (idempotente)."""
    from src.utils import cripto
    if not cripto.cifrado_disponible():
        return
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_empresa, api_key, api_secret FROM ecommerce_config")
        filas = cur.fetchall()
        for row in filas:
            d = row if isinstance(row, dict) else dict(zip(["id_empresa", "api_key", "api_secret"], row))
            cambios = {k: cripto.cifrar(d[k]) for k in ("api_key", "api_secret")
                       if d.get(k) and not cripto.parece_cifrado(d[k])}
            if cambios:
                sets = ", ".join(f"{k}=%s" for k in cambios)
                cur.execute(f"UPDATE ecommerce_config SET {sets} WHERE id_empresa=%s",
                            (*cambios.values(), d["id_empresa"]))
        conn.commit()
