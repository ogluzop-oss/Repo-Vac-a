"""
Portal Web (Back Office) · Acceso (Fase WEB-04). Decide qué secciones ve un empleado COMPONIENDO los sistemas
EXISTENTES: Entitlements (`saas.entitlements`), licencia/módulo SaaS (`saas.licensing`), RBAC
(`services.autorizacion`), rol y tenant (`id_empresa`/`id_tienda`). NUNCA implementa permisos propios ni
duplica reglas. La visibilidad del menú NO sustituye al enforcement real (que hacen los servicios al ejecutar
la acción); es la capa de navegación (igual patrón que el gate de menú del escritorio).
"""

import logging

from src.portal_web import navegacion

logger = logging.getLogger("portal_web.acceso")


def puede_ver(seccion: dict, usuario=None, id_empresa=None) -> bool:
    """True si la sección debe mostrarse. Orden: rol → entitlement → módulo SaaS → permiso RBAC."""
    # 1) Rol (si la sección lo restringe). El rol sale del usuario autenticado.
    roles = seccion.get("roles")
    if roles:
        rol = (usuario or {}).get("perfil") or (usuario or {}).get("rol")
        if rol and rol not in roles:
            return False

    # 2) Entitlement (capability) — reutiliza el resolver central.
    cap = seccion.get("capability")
    if cap:
        try:
            from src.services.saas import entitlements
            if not entitlements.has(cap, id_empresa=id_empresa):
                return False
        except Exception as e:
            logger.debug("entitlement %s: %s", cap, e)

    # 3) Módulo SaaS (licencia) — reutiliza licensing (legacy sin licencia = permitido).
    mod = seccion.get("modulo")
    if mod:
        try:
            from src.services.saas import licensing
            if not licensing.modulo_habilitado(mod, id_empresa=id_empresa):
                return False
        except Exception as e:
            logger.debug("modulo %s: %s", mod, e)

    # 4) Permiso RBAC (si se especifica y hay usuario) — reutiliza services.autorizacion.
    perm = seccion.get("permiso")
    if perm and usuario is not None:
        try:
            from src.services import autorizacion
            if not autorizacion.puede(usuario, perm, id_empresa=id_empresa):
                return False
        except Exception as e:
            logger.debug("rbac %s: %s", perm, e)
    return True


def secciones_visibles(usuario=None, id_empresa=None) -> list:
    """Secciones que el empleado puede ver (menú del portal), filtradas por RBAC+Entitlements+licencia+rol."""
    return [dict(s) for s in navegacion.SECCIONES if puede_ver(s, usuario, id_empresa)]
