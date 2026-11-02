"""
Registro de "pestañas" (secciones internas de un módulo) que pueden concederse/denegarse a un
usuario concreto desde Seguridad · Reglas de acceso — un nivel más fino que el módulo completo
(gestionado desde Seguridad · Roles, ver `modulos_menu.py`).

Resolución vía ACL (`acl_recursos`, recurso_tipo="pestana") — mismo patrón bespoke que
`menu_principal.py::_acceso_modulo` ya usa para módulos completos; no pasa por
`autorizacion.puede()` (evita tocar el motor central de permisos usado en toda la app).

Semántica de acceso (aclarada por el usuario): conceder una pestaña a un usuario que NO tiene
acceso completo al módulo padre le deja ENTRAR a ese módulo, pero viendo ÚNICAMENTE la(s)
pestaña(s) concedida(s) — no todas. Un usuario con acceso COMPLETO al módulo (por perfil o por
concesión de módulo en Seguridad · Roles) sigue viendo TODAS sus pestañas por defecto; una regla de
pestaña sobre él solo sirve para DENEGARLE una en concreto (ver `ubicacion.gps_interno`, abierta a
todos por defecto pero denegable a un usuario puntual).

Cada entrada de `REGISTRO` lleva su propio "por defecto" para ADMINISTRADOR/OPERARIO (no se hereda
ciegamente del módulo): la mayoría de las pestañas de un módulo íntegramente restringido son
`False`/`False` (nadie las tiene salvo concesión), pero una pestaña de un módulo ABIERTO puede
tener su propio matiz (p. ej. GPS Interno, abierta a ambos perfiles).
"""

REGISTRO = [
    # (pestana_id, etiqueta, módulo_padre, v_id_modulo, default_administrador, default_operario)
    ("contabilidad.plan", "Plan de cuentas", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.diario", "Diario", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.mayor", "Mayor", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.balances", "Balances", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.gastos", "Gastos", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.iva", "Libros IVA", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.cierres", "Cierres", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.aeat", "AEAT", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.libro_ing", "Libro de Ingresos", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.libro_gas", "Libro de Gastos", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.auditoria", "Informe Auditoría", "Contabilidad", "contabilidad", False, False),
    ("contabilidad.calc_fiscal", "Calculadora Fiscal", "Contabilidad", "contabilidad", False, False),
    ("ubicacion.gestion_estructura", "Gestión Estructura", "Ubicación", "ubicacion", True, False),
    ("ubicacion.gps_interno", "GPS Interno", "Ubicación", "ubicacion", True, True),

    # Clientes (v_id clientes_crm) — src/gui/crm_dashboard.py
    # (la antigua pestaña "Contactos"/leads se fusionó dentro de "clientes_crm.clientes" — ver
    # `src/gui/clientes_gui.py`; no queda como pestaña independiente, así que se retira su entrada.)
    # (la antigua pestaña "SAT / Postventa" se MIGRÓ a su propio módulo de nivel superior —
    # tarjeta "Posventa", v_id "sat", en `menu_principal.py`/`modulos_menu.py` — ya no vive como
    # pestaña de este módulo, así que se retira su entrada.)
    ("clientes_crm.oportunidades", "Oportunidades", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.kpis", "KPIs / Previsión", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.campanias", "Campañas", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.objetivos", "Objetivos", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.rutas", "Rutas", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.actividades", "Actividades", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.clientes", "Clientes", "Clientes", "clientes_crm", False, False),
    ("clientes_crm.presupuestos", "Presupuestos", "Clientes", "clientes_crm", False, False),

    # Tesorería (v_id tesoreria) — src/gui/tesoreria_gui.py
    ("tesoreria.posicion", "Posición", "Tesorería", "tesoreria", False, False),
    ("tesoreria.cuentas", "Cuentas", "Tesorería", "tesoreria", False, False),
    ("tesoreria.movimientos", "Movimientos", "Tesorería", "tesoreria", False, False),
    ("tesoreria.vencimientos", "Vencimientos", "Tesorería", "tesoreria", False, False),
    ("tesoreria.recordatorios", "Recordatorios de cobro", "Tesorería", "tesoreria", False, False),
    ("tesoreria.conciliacion", "Conciliación", "Tesorería", "tesoreria", False, False),
    ("tesoreria.banca", "Banca en línea", "Tesorería", "tesoreria", False, False),
    ("tesoreria.remesas", "Remesas SEPA", "Tesorería", "tesoreria", False, False),
    ("tesoreria.cashflow", "Flujo de caja", "Tesorería", "tesoreria", False, False),
    ("tesoreria.prevision", "Previsión", "Tesorería", "tesoreria", False, False),
    ("tesoreria.finanzas_avanzadas", "Finanzas Avanzadas", "Tesorería", "tesoreria", False, False),

    # Centro de Inteligencia (v_id bi) — src/gui/inteligencia_gui.py
    ("bi.dashboard_ejecutivo", "Dashboard Ejecutivo", "Centro de Inteligencia", "bi", False, False),
    ("bi.centro_actividad", "Centro de Actividad", "Centro de Inteligencia", "bi", False, False),
    ("bi.gemelo_digital", "Gemelo Digital", "Centro de Inteligencia", "bi", False, False),
    ("bi.prediccion", "Predicción", "Centro de Inteligencia", "bi", False, False),
    ("bi.simulador", "Simulador", "Centro de Inteligencia", "bi", False, False),
    ("bi.bi_corporativo", "BI Corporativo", "Centro de Inteligencia", "bi", False, False),

    # Permisos (v_id seguridad) — src/gui/seguridad_gui.py (este mismo módulo)
    ("seguridad.roles", "Roles", "Permisos", "seguridad", False, False),
    ("seguridad.reglas_acceso", "Reglas de acceso", "Permisos", "seguridad", False, False),
    ("seguridad.grupos", "Grupos", "Permisos", "seguridad", False, False),
    ("seguridad.gobierno", "Gobierno", "Permisos", "seguridad", False, False),
    ("seguridad.dr", "Disaster Recovery", "Permisos", "seguridad", False, False),
    ("seguridad.resiliencia", "Resiliencia", "Permisos", "seguridad", False, False),
    ("seguridad.rgpd", "RGPD", "Permisos", "seguridad", False, False),
    ("seguridad.password_politica", "Política de contraseñas", "Permisos", "seguridad", False, False),
    ("seguridad.incidentes", "Incidentes", "Permisos", "seguridad", False, False),
    ("seguridad.sesiones", "Sesiones activas", "Permisos", "seguridad", False, False),

    # RRHH (v_id rrhh) — src/gui/rrhh_gestion.py
    ("rrhh.empleados", "Empleados", "RRHH", "rrhh", False, False),
    ("rrhh.contratos", "Contratos", "RRHH", "rrhh", False, False),
    ("rrhh.nominas", "Nóminas", "RRHH", "rrhh", False, False),
    ("rrhh.altas", "Altas laborales", "RRHH", "rrhh", False, False),
    ("rrhh.bajas", "Bajas laborales", "RRHH", "rrhh", False, False),
    ("rrhh.finiquitos", "Finiquitos", "RRHH", "rrhh", False, False),
    ("rrhh.cert_empresa", "Certificados de empresa", "RRHH", "rrhh", False, False),
    ("rrhh.cert_laboral", "Certificados laborales", "RRHH", "rrhh", False, False),
    ("rrhh.cartas_despido", "Cartas de despido", "RRHH", "rrhh", False, False),
    ("rrhh.periodo_prueba", "Periodo prueba no superado", "RRHH", "rrhh", False, False),
    ("rrhh.rrhh_pro", "RRHH Pro", "RRHH", "rrhh", False, False),

    # Proyectos (v_id proyectos) — src/gui/proyectos_gui.py
    ("proyectos.kanban", "Tablero (Kanban)", "Proyectos", "proyectos", False, False),
    ("proyectos.cronograma", "Cronograma", "Proyectos", "proyectos", False, False),
    ("proyectos.seguimiento", "Horas y costes", "Proyectos", "proyectos", False, False),

    # Reparto (v_id transporte) — src/gui/transporte_gui.py
    ("transporte.flota", "Flota", "Reparto", "transporte", False, False),
    ("transporte.rutas", "Rutas de reparto", "Reparto", "transporte", False, False),

    # Proveedores/Autonomía IA/Automatización/Aprobaciones/Distribución: sin pestañas internas
    # (ventanas de vista única, confirmado) — no hay nada que registrar más allá de la concesión
    # de módulo completo que ya gestiona la pestaña "Roles".
]

_POR_ID = {pid: (etq, mod, v_id) for pid, etq, mod, v_id, *_r in REGISTRO}
_DEFAULTS = {pid: (da, do) for pid, _e, _m, _v, da, do in REGISTRO}


def opciones():
    """Lista (etiqueta, pestana_id) — TODAS las pestañas registradas, sin filtrar por perfil."""
    return [(f"{etq} ({mod})", pid) for pid, etq, mod, *_r in REGISTRO]


def opciones_para_perfil(perfil):
    """Lista (etiqueta, pestana_id) filtrada a lo relevante para `perfil` (ADMINISTRADOR/OPERARIO):
    pestañas que NO tiene por defecto (candidatas a "Permitir acceso") + pestañas que sí tiene por
    defecto pero están registradas para poder denegárselas puntualmente (p. ej. GPS Interno)."""
    perfil = (perfil or "").upper()
    idx = 0 if perfil == "ADMINISTRADOR" else 1
    out = []
    for pid, etq, mod, v_id, da, do in REGISTRO:
        default = da if idx == 0 else do
        out.append((f"{etq} ({mod})", pid))
    return out


def etiqueta(pestana_id):
    info = _POR_ID.get(pestana_id)
    return f"{info[0]} ({info[1]})" if info else pestana_id


def _acl_fila(recurso_tipo, recurso_id, usuario):
    """Fila ACL explícita de este usuario para `recurso_id`, o None si no hay ninguna."""
    uid = (usuario or {}).get("id")
    if not uid:
        return None
    try:
        from src.db import rbac
        emp = (usuario or {}).get("id_empresa")
        for r in rbac.listar_acl(recurso_tipo=recurso_tipo, recurso_id=recurso_id, id_empresa=emp):
            if r.get("sujeto_tipo") == "usuario" and str(r.get("sujeto_id")) == str(uid):
                return r
    except Exception:
        pass
    return None


def visible(pestana_id, usuario, default: bool) -> bool:
    """Resuelve si `usuario` ve la sub-pestaña `pestana_id`: una regla ACL explícita (Seguridad ·
    Reglas de acceso) prevalece, en cualquier dirección, sobre `default`. SUPERADMIN siempre ve
    todo (mismo criterio que `menu_principal.py::_acceso_modulo`)."""
    perfil = str((usuario or {}).get("perfil") or "").upper()
    if perfil == "SUPERADMIN":
        return True
    if not (usuario or {}).get("id"):
        return default
    fila = _acl_fila("pestana", pestana_id, usuario)
    return bool(fila["permitido"]) if fila is not None else default


def tiene_modulo_completo(v_id, usuario, default_modulo: bool) -> bool:
    """¿Tiene `usuario` acceso COMPLETO (todas las pestañas) al módulo `v_id`? Replica el criterio
    de `menu_principal.py::_acceso_modulo` (perfil por defecto + ACL de módulo completo de
    Seguridad · Roles) para que cada módulo sepa si debe mostrar todas sus pestañas por defecto o
    solo las concedidas sueltas."""
    perfil = str((usuario or {}).get("perfil") or "").upper()
    if perfil == "SUPERADMIN":
        return True
    if not (usuario or {}).get("id"):
        return default_modulo
    fila = _acl_fila("modulo", v_id, usuario)
    return bool(fila["permitido"]) if fila is not None else default_modulo


def tiene_alguna_pestana_permitida(v_id, usuario) -> bool:
    """¿Tiene `usuario` al menos una pestaña CONCEDIDA (ACL "permitir") bajo el módulo `v_id`? Se
    usa para dejarle ENTRAR al módulo aunque no tenga acceso completo — solo verá esa(s)
    pestaña(s), nunca las demás (ver `tiene_modulo_completo`, que decide el "por defecto" de cada
    pestaña individual una vez dentro)."""
    perfil = str((usuario or {}).get("perfil") or "").upper()
    if perfil == "SUPERADMIN":
        return True
    uid = (usuario or {}).get("id")
    if not uid:
        return False
    try:
        from src.db import rbac
        emp = (usuario or {}).get("id_empresa")
        prefijo = f"{v_id}."
        for r in rbac.listar_acl(recurso_tipo="pestana", id_empresa=emp):
            if (r.get("sujeto_tipo") == "usuario" and str(r.get("sujeto_id")) == str(uid)
                    and str(r.get("recurso_id") or "").startswith(prefijo) and r.get("permitido")):
                return True
    except Exception:
        pass
    return False
