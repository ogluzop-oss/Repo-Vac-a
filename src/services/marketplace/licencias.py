"""
Marketplace · Licencias (Fase IV · Bloque 2) — SOLO arquitectura (sin cobro). Modela licencias por
empresa / tienda / usuario / temporal / enterprise sobre `marketplace_licencias`. Multiempresa
estricto. Comprobar licencia es un gate opcional de instalación/uso (degradable: sin licencia
requerida por defecto).
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("marketplace.licencias")

EMPRESA, TIENDA, USUARIO, TEMPORAL, ENTERPRISE = (
    "empresa", "tienda", "usuario", "temporal", "enterprise")
TIPOS = (EMPRESA, TIENDA, USUARIO, TEMPORAL, ENTERPRISE)


def conceder(clave_plugin, *, id_empresa=None, tipo=EMPRESA, alcance_id=None,
             valido_hasta=None) -> bool:
    if tipo not in TIPOS:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO marketplace_licencias (id_empresa, clave_plugin, tipo, alcance_id, "
                "valido_hasta, estado) VALUES (%s,%s,%s,%s,%s,'activa')",
                (id_empresa, clave_plugin, tipo, alcance_id, valido_hasta))
            conn.commit()
        return True
    except Exception as e:
        logger.error("conceder(%s): %s", clave_plugin, e)
        return False


def revocar(clave_plugin, *, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE marketplace_licencias SET estado='revocada' WHERE clave_plugin=%s "
                        "AND (id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL))",
                        (clave_plugin, id_empresa, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("revocar(%s): %s", clave_plugin, e)
        return False


def listar(id_empresa=None, *, clave_plugin=None) -> list:
    q = ("SELECT * FROM marketplace_licencias WHERE (id_empresa=%s OR id_empresa IS NULL) "
         "AND estado='activa'")
    p = [id_empresa]
    if clave_plugin:
        q += " AND clave_plugin=%s"; p.append(clave_plugin)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar licencias: %s", e)
        return []


def tiene_licencia(clave_plugin, *, id_empresa=None, id_tienda=None, id_usuario=None,
                   requerir=False) -> bool:
    """¿Existe licencia válida para (empresa, tienda?, usuario?)? Si `requerir` es False y no hay
    ninguna licencia registrada para el plugin, se permite (modelo abierto por defecto, sin cobro)."""
    licencias = listar(id_empresa, clave_plugin=clave_plugin)
    if not licencias:
        return not requerir
    ahora = datetime.now()
    for lic in licencias:
        hasta = lic.get("valido_hasta")
        if hasta and isinstance(hasta, datetime) and hasta < ahora:
            continue
        tipo = lic.get("tipo")
        alcance = lic.get("alcance_id")
        if tipo in (EMPRESA, ENTERPRISE, TEMPORAL):
            return True
        if tipo == TIENDA and (alcance is None or str(alcance) == str(id_tienda)):
            return True
        if tipo == USUARIO and (alcance is None or str(alcance) == str(id_usuario)):
            return True
    return False


__all__ = ["TIPOS", "EMPRESA", "TIENDA", "USUARIO", "TEMPORAL", "ENTERPRISE",
           "conceder", "revocar", "listar", "tiene_licencia"]
