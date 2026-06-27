"""
Branding multitenant (FASE SAAS-J). Configuración visual/documental por empresa.
"""

import logging
from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("saas.branding")
_CAMPOS = ("nombre_comercial", "logo_ruta", "color_primario", "color_secundario",
           "dominio", "correo_principal", "pie_documental")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def set_branding(id_empresa=None, **campos) -> bool:
    id_empresa = _emp(id_empresa)
    datos = {k: campos.get(k) for k in _CAMPOS if k in campos}
    if not datos:
        return False
    cols = ", ".join(datos.keys())
    ph = ", ".join(["%s"] * len(datos))
    upd = ", ".join(f"{k}=VALUES({k})" for k in datos)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO empresa_branding (id_empresa, {cols}) VALUES (%s, {ph}) "
                        f"ON DUPLICATE KEY UPDATE {upd}", (id_empresa, *datos.values()))
            conn.commit()
        _audit(id_empresa)
        return True
    except Exception as e:
        logger.error("set_branding: %s", e)
        return False


def obtener_branding(id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM empresa_branding WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if not r:
                return {}
            return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
    except Exception as e:
        logger.error("obtener_branding: %s", e)
        return {}


def _audit(id_empresa):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "BRANDING_ACTUALIZADO", "empresa_branding", str(id_empresa))
    except Exception:
        pass
