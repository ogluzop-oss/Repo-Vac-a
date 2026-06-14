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
                (id_empresa, nueva["plataforma"], nueva["base_url"], nueva["api_key"],
                 nueva["api_secret"], nueva["estado"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False
