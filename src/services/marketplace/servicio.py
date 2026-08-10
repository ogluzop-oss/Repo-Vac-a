"""
Marketplace · Servicio (Fase IV · Bloque 2). Fachada que orquesta catálogo + validación + firmas +
dependencias + licencias + instalación + actualización, aplicando la POLÍTICA de cada empresa
(oficiales | firmados | internos | todos, en `marketplace_politica`). Punto único que consumen la
GraphQL Layer y la GUI. Multiempresa estricto.
"""

from __future__ import annotations

import logging

from src.db.conexion import ensure_schema, obtener_conexion
from src.services.marketplace import catalogo as _catalogo
from src.services.marketplace import instalacion as _inst

logger = logging.getLogger("marketplace.servicio")

POLITICAS = ("oficiales", "firmados", "internos", "todos")
POLITICA_DEFECTO = "firmados"


def politica(id_empresa=None) -> str:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT politica FROM marketplace_politica WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
        if r:
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) or POLITICA_DEFECTO
    except Exception as e:
        logger.debug("politica(%s): %s", id_empresa, e)
    return POLITICA_DEFECTO


def fijar_politica(politica_valor, *, id_empresa=None) -> bool:
    if politica_valor not in POLITICAS or not id_empresa:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO marketplace_politica (id_empresa, politica) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE politica=VALUES(politica), actualizado=NOW()",
                        (id_empresa, politica_valor))
            conn.commit()
        return True
    except Exception as e:
        logger.error("fijar_politica: %s", e)
        return False


def _revocadas(id_empresa):
    """Lista de plugins/hashes revocados (preparado; hoy vacío o vía licencias revocadas)."""
    try:
        from src.services.marketplace import licencias
        return {lic["clave_plugin"] for lic in licencias.listar(id_empresa) if lic.get("estado") == "revocada"}
    except Exception:
        return set()


# ── API pública (consumida por GraphQL/GUI) ────────────────────────────────────
def catalogo(id_empresa=None, *, categoria=None, texto=""):
    return _catalogo.catalogo(id_empresa, categoria=categoria, texto=texto)


def categorias(id_empresa=None):
    return _catalogo.categorias(id_empresa)


def detalle(clave, id_empresa=None):
    return _catalogo.detalle(clave, id_empresa)


def instalar(clave, *, id_empresa=None, usuario=None, origen=None, requerir_licencia=False):
    """Instala aplicando la política de la empresa (y la lista de revocados)."""
    return _inst.instalar(clave, id_empresa=id_empresa, usuario=usuario,
                          politica=politica(id_empresa), revocadas=_revocadas(id_empresa),
                          requerir_licencia=requerir_licencia)


def desinstalar(clave, *, id_empresa=None, usuario=None):
    return _inst.desinstalar(clave, id_empresa=id_empresa, usuario=usuario)


def reinstalar(clave, *, id_empresa=None, usuario=None):
    return _inst.reinstalar(clave, id_empresa=id_empresa, usuario=usuario,
                            politica=politica(id_empresa), revocadas=_revocadas(id_empresa))


def rollback(clave, *, id_empresa=None, usuario=None):
    return _inst.rollback(clave, id_empresa=id_empresa, usuario=usuario)


def verificar_integridad(clave, *, id_empresa=None):
    return _inst.verificar_integridad(clave, id_empresa=id_empresa)


def historial(clave, id_empresa=None):
    return _inst.historial(clave, id_empresa)


def actualizar(clave, *, id_empresa=None, usuario=None):
    from src.services.marketplace import actualizacion
    return actualizacion.actualizar(clave, id_empresa=id_empresa, usuario=usuario,
                                    politica=politica(id_empresa), revocadas=_revocadas(id_empresa))


def actualizaciones_disponibles(id_empresa=None):
    from src.services.marketplace import actualizacion
    return actualizacion.actualizaciones_disponibles(id_empresa)


__all__ = ["POLITICAS", "POLITICA_DEFECTO", "politica", "fijar_politica", "catalogo", "categorias",
           "detalle", "instalar", "desinstalar", "reinstalar", "rollback", "verificar_integridad",
           "historial", "actualizar", "actualizaciones_disponibles"]
