"""
Portal Web (Back Office) · Layout (Fase WEB-04). Contratos de LAYOUT/SIDEBAR/NAVBAR como DATOS (arquitectura,
no interfaz definitiva). El frontend (web hoy, móvil en el futuro) renderiza estos descriptores. Multiempresa
por `id_empresa`/`id_tienda` (nunca por dominio). Reutiliza `acceso` (RBAC+Entitlements+licencia).
"""

from src.portal_web import acceso


def sidebar(usuario=None, id_empresa=None) -> dict:
    """Menú lateral: sólo las secciones visibles para el empleado (ya filtradas)."""
    return {"secciones": [{"clave": s["clave"], "titulo": s["titulo"], "icono": s["icono"]}
                          for s in acceso.secciones_visibles(usuario, id_empresa)]}


def navbar(usuario=None, id_empresa=None, id_tienda=None) -> dict:
    """Barra superior: contexto del usuario/tenant (sin secretos)."""
    u = usuario or {}
    return {"usuario": {"id": u.get("id"), "nombre": u.get("nombre"), "rol": u.get("perfil") or u.get("rol")},
            "id_empresa": id_empresa, "id_tienda": id_tienda,
            "acciones": ["perfil", "notificaciones", "logout"]}


def layout(usuario=None, id_empresa=None, id_tienda=None) -> dict:
    """Layout completo del portal (navbar + sidebar + área de contenido). Reutilizable por móvil."""
    return {"tipo": "back_office", "navbar": navbar(usuario, id_empresa, id_tienda),
            "sidebar": sidebar(usuario, id_empresa),
            "contenido": {"seccion_inicial": "inicio", "responsive": True, "reutilizable_movil": True}}
