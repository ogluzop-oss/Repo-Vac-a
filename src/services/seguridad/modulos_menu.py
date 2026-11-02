"""
Fuente única de los módulos del menú principal y su visibilidad por defecto según perfil.

Extraído de `menu_principal.py` (antes hardcodeado e inline, una condición por tarjeta) y de
`seguridad_gui.py` (que duplicaba a mano `_MODULOS_MENU`/`_MODULOS_EDICION` solo para poblar un
desplegable). Ambos ahora leen de aquí — sin lógica nueva, mismo comportamiento de siempre.

SUPERADMIN nunca se resuelve contra estas tablas (tiene acceso completo por su propio atajo, tanto
en `menu_principal.py` como en la capa ACL de `services.seguridad.pestanas_app`).
"""

MODULOS = [   # (v_id, etiqueta) — mismo orden/contenido que _MODULOS_MENU tenía en seguridad_gui.py
    ("tpv", "TPV"), ("logistica", "Logística"), ("stock", "Stock"), ("ubicacion", "Ubicación"),
    ("info", "Artículo"), ("documentos", "Documentos"), ("correo", "Correo"), ("mermas", "Mermas"),
    ("etiquetas", "Etiquetas"), ("reposicion", "Reposición"), ("ventas", "Ventas"),
    ("catalogo", "Catálogo Web"), ("gestion_caja", "Gestión Caja"), ("compras", "Proveedores"),
    ("clientes_crm", "Clientes"), ("contabilidad", "Contabilidad"), ("tesoreria", "Tesorería"),
    ("bi", "Centro de Inteligencia"), ("seguridad", "Permisos"), ("workflow", "Tareas"),
    ("autonomia_ia", "Autonomía IA"), ("automatizacion", "Automatización"),
    ("aprobaciones", "Aprobaciones"),
    ("registro_temperatura", "Temperaturas"), ("saas", "SaaS"),
    ("rrhh", "RRHH"), ("proyectos", "Proyectos"), ("portal", "Portal del empleado"),
    ("incidencias", "Incidencias"),
    ("almacenes", "Almacenes"), ("migracion", "Migrar datos"), ("camaras", "Cámaras"),
    ("recetas", "Recetas"), ("obrador", "Obrador"),
    ("transporte", "Reparto"), ("distribucion", "Distribución"), ("mrp", "Producción"),
    ("gmao", "Mantenimiento"), ("fichajes", "Fichajes"), ("horarios", "Horarios"),
    ("sat", "Posventa"), ("redes_sociales", "RRSS"), ("nominas", "Nóminas"),
]

# v_id de módulo → clave de función segmentable (`services.verticales.FUNCIONES`) para los módulos
# que solo existen en determinadas ediciones — mismo gateo que aplica `menu_principal.py`.
MODULOS_EDICION = {
    "catalogo": "catalogo.web",
    "recetas": "pharmacy.recetas",
    "obrador": "bakery.obrador",
    "transporte": "transporte.reparto",
    "distribucion": "distribucion.expedicion",
    "mrp": "almacenes.mrp",
}

# Visibilidad POR DEFECTO hoy (confirmado leyendo cada condición de menu_principal.py línea a
# línea) — un v_id ausente de ambos conjuntos es False por defecto para ambos perfiles
# (compras, clientes_crm, contabilidad, tesoreria, bi, seguridad, autonomia_ia, automatizacion,
# aprobaciones, rrhh, proyectos, transporte, distribucion, saas → SUPERADMIN-only hoy).
# "redes_sociales" (petición explícita): EXCLUSIVO de SUPERADMIN, ausente a propósito de ambos
# conjuntos — ver también el doble gate explícito en `menu_principal.py`.
DEFAULT_ADMINISTRADOR = frozenset({
    "tpv", "logistica", "stock", "ubicacion", "info", "documentos", "correo", "mermas",
    "etiquetas", "reposicion", "ventas", "catalogo", "gestion_caja", "workflow",
    "registro_temperatura", "portal", "almacenes", "migracion", "camaras", "recetas",
    "obrador", "mrp", "gmao", "fichajes", "horarios", "sat", "incidencias", "nominas",
})
DEFAULT_OPERARIO = frozenset({
    "tpv", "logistica", "stock", "ubicacion", "info", "mermas", "reposicion", "workflow",
    "registro_temperatura", "portal", "fichajes", "horarios", "sat", "nominas",
})
# "horarios" SÍ se añade a DEFAULT_OPERARIO (RRHH Fase E, bolsa de horas): OPERARIO ahora entra
# al módulo Horarios en modo SOLO LECTURA (sin ningún botón de edición) para poder usar el único
# botón que ve ahí, "Bolsa de horas", sobre su propia ficha — ver el gate explícito y el modo de
# solo lectura en `menu_principal.py`/`horarios_gui.py`/`rrhh/gui/horarios.py`. Antes de esta fase
# el módulo estaba vedado por completo a OPERARIO; la exclusión total queda revertida a propósito.
# "nominas" (petición explícita, F4.10 cierre de brecha): visible para ADMINISTRADOR y OPERARIO,
# EXCLUIDO de SUPERADMIN — mismo criterio inverso que "sat" (se oculta al perfil de MÁS privilegio,
# no al de menos). SUPERADMIN gestiona/aprueba nóminas desde RRHH; este módulo es la autoconsulta
# de la nómina PROPIA de cada trabajador con cuenta vinculada (`rrhh.portal_servicio`).


def disponibles(id_empresa=None):
    """`MODULOS` filtrado a los que existen en la edición activa, con un «-» inicial (sin
    seleccionar ninguno) — mismo comportamiento que `_modulos_disponibles()` tenía en
    seguridad_gui.py."""
    from src.services import verticales
    opciones = [("-", None)]
    for v_id, texto in MODULOS:
        funcion = MODULOS_EDICION.get(v_id)
        if funcion and not verticales.visible(funcion, id_empresa=id_empresa):
            continue
        opciones.append((texto, v_id))
    return opciones


def default_visible(v_id, perfil) -> bool:
    """¿Ve `v_id` por defecto un usuario de `perfil` (ADMINISTRADOR/OPERARIO), antes de aplicar
    cualquier regla ACL explícita? SUPERADMIN no debería llamarse con esta función (tiene acceso
    completo por su propio atajo), pero por seguridad no bloquea si se le pasa."""
    perfil = (perfil or "").upper()
    if perfil == "ADMINISTRADOR":
        return v_id in DEFAULT_ADMINISTRADOR
    if perfil == "OPERARIO":
        return v_id in DEFAULT_OPERARIO
    return True
