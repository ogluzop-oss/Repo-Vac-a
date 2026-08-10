"""
Portal Web (Back Office) · Navegación (Fase WEB-04). Registro DECLARATIVO de las secciones del portal para
empleados: es la arquitectura de sidebar/routing como DATOS. Cada sección referencia el MÓDULO SaaS y/o la
CAPABILITY (entitlement) que la habilitan y el SERVICIO existente que consumirá (nunca duplica lógica). El
control de acceso real lo compone `acceso.py` reutilizando RBAC + Entitlements + licencia + tenant.

NO implementa negocio ni permisos propios: sólo describe QUÉ secciones existen y CON QUÉ se habilitan/consumen.
Preparado para reutilizarse parcialmente por la futura app móvil.
"""

# Cada sección: clave · titulo · icono · modulo(SaaS)|None · capability(entitlement)|None · roles|None ·
# servicio(informativo: qué servicio EXISTENTE consume) · acciones(previstas).
SECCIONES = (
    {"clave": "inicio", "titulo": "Inicio", "icono": "dashboard", "modulo": None, "capability": None,
     "servicio": "services.bi / observabilidad", "acciones": ["dashboard", "kpis", "alertas", "resumen"]},
    {"clave": "clientes", "titulo": "Clientes", "icono": "clientes", "modulo": "clientes", "capability": None,
     "servicio": "db.clientes / services.crm", "acciones": ["consultar", "crear", "editar", "eliminar", "historial"]},
    {"clave": "articulos", "titulo": "Artículos", "icono": "articulos", "modulo": "inventario", "capability": None,
     "servicio": "db.articulos / db.catalogo", "acciones": ["consultar", "buscar", "filtrar", "editar", "stock", "precios"]},
    {"clave": "pedidos", "titulo": "Pedidos", "icono": "pedidos", "modulo": "ventas", "capability": None,
     "servicio": "services.ventas / pedidos", "acciones": ["crear", "editar", "consultar", "cambiar_estado"]},
    {"clave": "encargos", "titulo": "Encargos", "icono": "encargos", "modulo": "ventas", "capability": None,
     "servicio": "services.ventas (encargos)", "acciones": ["crear", "preparar", "entregar"]},
    {"clave": "reservas", "titulo": "Reservas", "icono": "reservas", "modulo": "ventas", "capability": None,
     "servicio": "comercio_digital.pickup / transacciones", "acciones": ["consultar", "crear", "cancelar"]},
    {"clave": "stock", "titulo": "Stock", "icono": "stock", "modulo": "inventario", "capability": None,
     "servicio": "db.kardex / db.stock_almacen", "acciones": ["consultar", "movimientos", "inventarios", "almacenes"]},
    {"clave": "reabastecimiento", "titulo": "Reabastecimiento", "icono": "reabastecimiento", "modulo": "inventario",
     "capability": None, "servicio": "services.reabastecimiento", "acciones": ["sugerencias", "lanzar_pedidos"]},
    {"clave": "logistica", "titulo": "Logística", "icono": "logistica", "modulo": "inventario", "capability": "multi_tienda.enabled",
     "servicio": "db.logistica / traspasos", "acciones": ["traspasos", "preparacion", "recepcion"]},
    {"clave": "caja", "titulo": "Caja", "icono": "caja", "modulo": "tpv", "capability": None,
     "servicio": "db.caja", "acciones": ["movimientos", "cierres"]},  # sin TPV web todavía
    {"clave": "rrhh", "titulo": "RRHH", "icono": "rrhh", "modulo": "rrhh", "capability": None,
     "servicio": "src.rrhh", "acciones": ["empleados", "contratos", "vacaciones"]},
    {"clave": "documentos", "titulo": "Documentos", "icono": "documentos", "modulo": None, "capability": None,
     "servicio": "db.documentos / storage.documentos", "acciones": ["consultar", "descargar", "subir"]},
    {"clave": "configuracion", "titulo": "Configuración", "icono": "config", "modulo": None, "capability": None,
     "roles": ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"),
     "servicio": "db.empresa / db.usuario / db.rbac", "acciones": ["empresa", "usuarios", "permisos", "roles"]},
)

_POR_CLAVE = {s["clave"]: s for s in SECCIONES}


def seccion(clave) -> dict | None:
    s = _POR_CLAVE.get(clave)
    return dict(s) if s else None


def descriptor() -> dict:
    """Descriptor público del módulo (sin datos de negocio)."""
    return {
        "modulo": "portal_web", "tipo": "back_office", "estado": "PREPARADO",
        "independiente_de": ["canal_web", "portal_cliente", "tpv"],
        "reutiliza": ["services", "db", "rbac", "entitlements", "jwt", "auditoria", "eventos",
                      "storage_provider", "secret_manager"],
        "multitenant": ["id_empresa", "id_tienda"], "no_por": "dominio",
        "secciones": [{"clave": s["clave"], "titulo": s["titulo"], "icono": s["icono"]} for s in SECCIONES],
    }
