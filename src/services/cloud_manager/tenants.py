"""
Cloud Manager · Tenants (Fase V · Bloque 7). Alta/baja/suspensión/reactivación de empresas SaaS y
backup/restauración, REUTILIZANDO el módulo SaaS existente (`services.saas.licensing`,
`services.saas.backup_tenant`) y el dominio de empresas (`db.empresa`). No crea un segundo sistema
multiempresa. Solo SUPERADMIN debería invocarlo (lo controla la GUI/API).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("cloud.tenants")


def crear(nombre, *, plan="basic", usuario=None, **campos) -> dict:
    """Crea una empresa y le asigna un plan (reutiliza empresa.crear_empresa + saas.licensing)."""
    try:
        from src.db.empresa import crear_empresa
        id_empresa = crear_empresa(nombre, **campos)
        if not id_empresa:
            return {"ok": False, "error": "no se pudo crear la empresa"}
        try:
            from src.services.saas import licensing
            licensing.asignar_plan(id_empresa, plan, estado="activa", usuario=usuario)
        except Exception as e:
            logger.debug("asignar_plan: %s", e)
        return {"ok": True, "id_empresa": id_empresa, "plan": plan}
    except Exception as e:
        logger.error("crear tenant: %s", e)
        return {"ok": False, "error": str(e)}


def _cambiar_estado(id_empresa, estado, *, usuario=None) -> dict:
    try:
        from src.services.saas import licensing
        actual = licensing.licencia_activa(id_empresa) or {}
        codigo = actual.get("codigo_plan") or actual.get("plan") or "basic"
        ok = licensing.asignar_plan(id_empresa, codigo, estado=estado, usuario=usuario)
        return {"ok": bool(ok), "id_empresa": id_empresa, "estado": estado}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def suspender(id_empresa, *, usuario=None) -> dict:
    return _cambiar_estado(id_empresa, "suspendida", usuario=usuario)


def reactivar(id_empresa, *, usuario=None) -> dict:
    return _cambiar_estado(id_empresa, "activa", usuario=usuario)


def eliminar(id_empresa, *, usuario=None) -> dict:
    """Baja SEGURA (soft): marca la licencia como cancelada (no borra datos). El borrado físico de
    una empresa es irreversible y queda fuera de este servicio por seguridad."""
    return _cambiar_estado(id_empresa, "cancelada", usuario=usuario)


def listar() -> list:
    """Empresas + su estado operativo (reutiliza empresa + saas.licensing)."""
    salida = []
    try:
        from src.db.empresa import listar_empresas
        from src.services.saas import licensing
        for e in listar_empresas():
            emp_id = e.get("id") or e.get("id_empresa")
            try:
                estado = licensing.estado_operativo(emp_id)
            except Exception:
                estado = "desconocido"
            salida.append({**e, "estado_operativo": estado})
    except Exception as ex:
        logger.debug("listar tenants: %s", ex)
    return salida


def backup(id_empresa=None) -> dict:
    try:
        from src.services.saas import backup_tenant
        return backup_tenant.exportar_empresa(id_empresa)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def restaurar(ruta, id_empresa=None) -> dict:
    try:
        from src.services.saas import backup_tenant
        return backup_tenant.restaurar_empresa(ruta, id_empresa)
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["crear", "suspender", "reactivar", "eliminar", "listar", "backup", "restaurar"]
