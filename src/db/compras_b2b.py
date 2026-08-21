"""
Configuración del conector B2B + reglas de precios del módulo Proveedores (por empresa).

Los secretos (api_key, api_secret) se cifran en reposo con Fernet (`utils.cripto`), igual que
`pasarela_config`/`correos_corporativos.smtp_*`. La pestaña Avanzado (RBAC + cifrado) escribe aquí; el
`b2b_client` y el motor de precios dinámicos leen de aquí.
"""

import logging

logger = logging.getLogger("db.compras_b2b")

_SECRETOS = ("api_key", "api_secret")


def _empresa(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def obtener_config(id_empresa=None) -> dict:
    """Config B2B de la empresa (con defaults). Descifra los secretos para su uso."""
    emp = _empresa(id_empresa)
    base = {"id_empresa": emp, "proveedor": "rest", "endpoint": "", "api_key": "", "api_secret": "",
            "entorno": "sandbox", "umbral_variacion_pct": 10.0, "margen_objetivo_pct": 30.0,
            "estado": "activo"}
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM compras_b2b_config WHERE id_empresa=%s", (emp,))
            r = _filas_a_dicts(cur, cur.fetchall())
        if r:
            row = r[0]
            base.update({k: (row.get(k) if row.get(k) is not None else base[k]) for k in base})
            base["umbral_variacion_pct"] = float(base["umbral_variacion_pct"] or 0)
            base["margen_objetivo_pct"] = float(base["margen_objetivo_pct"] or 0)
    except Exception as e:
        logger.debug("obtener_config: %s", e)
    try:
        from src.utils import cripto
        for k in _SECRETOS:
            base[k] = cripto.descifrar_seguro(base.get(k)) or ""
    except Exception:
        pass
    return base


def guardar_config(*, proveedor=None, endpoint=None, api_key=None, api_secret=None, entorno=None,
                   umbral_variacion_pct=None, margen_objetivo_pct=None, estado=None,
                   id_empresa=None) -> bool:
    """Upsert de la config B2B. Cifra los secretos. Un secreto vacío/None NO borra el existente."""
    emp = _empresa(id_empresa)
    actual = obtener_config(emp)
    from src.utils import cripto

    def _cif(v):
        return cripto.cifrar(v) if v else None
    nueva = {
        "proveedor": (proveedor or actual["proveedor"]),
        "endpoint": (endpoint if endpoint is not None else actual["endpoint"]),
        "api_key": (_cif(api_key) if api_key else (_cif(actual["api_key"]) if actual["api_key"] else None)),
        "api_secret": (_cif(api_secret) if api_secret
                       else (_cif(actual["api_secret"]) if actual["api_secret"] else None)),
        "entorno": (entorno or actual["entorno"]),
        "umbral_variacion_pct": float(umbral_variacion_pct if umbral_variacion_pct is not None
                                      else actual["umbral_variacion_pct"]),
        "margen_objetivo_pct": float(margen_objetivo_pct if margen_objetivo_pct is not None
                                     else actual["margen_objetivo_pct"]),
        "estado": (estado or actual["estado"]),
    }
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_b2b_config (id_empresa, proveedor, endpoint, api_key, api_secret, "
                "entorno, umbral_variacion_pct, margen_objetivo_pct, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE proveedor=VALUES(proveedor), endpoint=VALUES(endpoint), "
                "api_key=VALUES(api_key), api_secret=VALUES(api_secret), entorno=VALUES(entorno), "
                "umbral_variacion_pct=VALUES(umbral_variacion_pct), "
                "margen_objetivo_pct=VALUES(margen_objetivo_pct), estado=VALUES(estado)",
                (emp, nueva["proveedor"], nueva["endpoint"], nueva["api_key"], nueva["api_secret"],
                 nueva["entorno"], nueva["umbral_variacion_pct"], nueva["margen_objetivo_pct"],
                 nueva["estado"]))
            c.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False
