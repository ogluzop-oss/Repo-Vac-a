"""
Capa de datos de TIENDAS + cambio de contexto multitienda (F1).

Permite que un ADMINISTRADOR gestione las tiendas de SU empresa y que un
SUPERADMIN acceda a cualquier empresa/tienda, cambiando el TenantContext en
caliente (sin cerrar sesión) y dejando traza en `auditoria_logs`
(acción CAMBIO_CONTEXTO_TIENDA). Ver [[project_multitenant]] y
[[project_centro_documental]].
"""

import json
import logging

from src.db.conexion import (
    EMPRESA_DEFAULT_ID,
    _filas_a_dicts,
    ensure_schema,
    log_auditoria,
    obtener_conexion,
)

logger = logging.getLogger("tiendas_db")


def _cols(cur, tabla) -> set:
    cur.execute(f"SHOW COLUMNS FROM {tabla}")
    return {r["Field"] if isinstance(r, dict) else r[0] for r in cur.fetchall()}


def listar_tiendas(id_empresa: str | None = None) -> list[dict]:
    """Tiendas activas. Si se indica `id_empresa`, solo las de esa empresa
    (None = todas, para SUPERADMIN). Devuelve [{id, codigo_tienda, nombre,
    id_empresa}] ordenadas por código."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cols = _cols(cur, "tiendas")
            campos = ["id", "codigo_tienda", "nombre"]
            if "id_empresa" in cols:
                campos.append("id_empresa")
            filtros, params = [], []
            if "activo" in cols:
                filtros.append("COALESCE(activo,1)=1")
            if id_empresa and "id_empresa" in cols:
                filtros.append("id_empresa=%s"); params.append(id_empresa)
            where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
            cur.execute(
                f"SELECT {', '.join(campos)} FROM tiendas{where} ORDER BY codigo_tienda, id",
                params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_tiendas: %s", e)
        return []


def obtener_tienda(id_tienda) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tiendas WHERE id=%s", (id_tienda,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("Error obtener_tienda(%s): %s", id_tienda, e)
        return None


def puede_acceder(id_tienda) -> bool:
    """True si el usuario en sesión puede operar la tienda dada:
    SUPERADMIN → cualquiera; ADMINISTRADOR/GERENTE → solo las de SU empresa."""
    try:
        from src.db.usuario import sesion_global
        if sesion_global.es_superadmin():
            return True
        if not sesion_global.es_admin():
            return False
        t = obtener_tienda(id_tienda) or {}
        return (t.get("id_empresa") or EMPRESA_DEFAULT_ID) == sesion_global.empresa_id()
    except Exception:
        return False


def cambiar_contexto_tienda(id_tienda) -> dict | None:
    """Cambia la tienda (y empresa) ACTIVAS del proceso sin cerrar sesión, con
    control de acceso y traza de auditoría. Devuelve la tienda destino o None."""
    from src.db import empresa as emp_db
    from src.db.usuario import sesion_global

    tienda = obtener_tienda(id_tienda)
    if not tienda:
        return None
    if not puede_acceder(id_tienda):
        logger.warning("Acceso a tienda %s denegado para %s",
                       id_tienda, sesion_global.obtener_nombre())
        return None

    # Origen (para la traza) → destino.
    origen = {"empresa": emp_db.empresa_actual_id(), "tienda": emp_db.tienda_actual_id()}
    destino_empresa = tienda.get("id_empresa") or EMPRESA_DEFAULT_ID
    emp_db.set_empresa_actual(destino_empresa)
    emp_db.set_tienda_actual(tienda.get("id"))

    try:
        log_auditoria(
            usuario=sesion_global.obtener_nombre(),
            accion="CAMBIO_CONTEXTO_TIENDA",
            tabla_afectada="tiendas",
            detalles=json.dumps({
                "empresa_origen": origen["empresa"], "tienda_origen": origen["tienda"],
                "empresa_destino": destino_empresa, "tienda_destino": tienda.get("id"),
                "codigo_tienda": tienda.get("codigo_tienda"),
            }, ensure_ascii=False),
        )
    except Exception as e:
        logger.debug("No se pudo registrar CAMBIO_CONTEXTO_TIENDA: %s", e)
    logger.info("Contexto de tienda cambiado a %s (%s).",
                tienda.get("codigo_tienda"), tienda.get("nombre"))
    return tienda
