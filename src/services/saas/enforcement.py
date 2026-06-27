"""
Enforcement real de licencias SaaS (FASE P0.1/P0.3).

Punto central que conecta el LicensingService con el producto. Ofrece:
  • exigir_modulo(modulo)         → lanza LicenciaError si el plan no lo incluye (backend).
  • nivel_acceso(empresa)         → 'normal' | 'lectura' | 'bloqueado' según el estado de pago.
  • acceso_modulo(v_id, empresa)  → (permitido, motivo) para el gate del menú/GUI.

COMPATIBILIDAD LEGACY: sin licencia asignada → 'normal' y todo permitido (comportamiento actual
intacto). El enforcement solo actúa cuando la empresa tiene una licencia SaaS.
"""

import logging

from src.services.saas import licensing as _L

logger = logging.getLogger("saas.enforcement")

# Mapa identificador de menú (v_id) → módulo de licencia. Lo no mapeado es siempre accesible
# (login, menú, portal SaaS, notificaciones, seguridad: imprescindibles para operar/renovar).
MODULO_POR_VID = {
    "tpv": "tpv", "ventas": "ventas", "compras": "compras", "compras_avanzado": "compras",
    "clientes": "clientes", "clientes_crm": "clientes", "proveedores": "proveedores",
    "kardex": "inventario", "inventario_fisico": "inventario", "lotes": "inventario",
    "stock_almacen": "inventario", "almacenes": "inventario",
    "rrhh": "rrhh", "portal": "rrhh", "contabilidad": "contabilidad",
    "tesoreria": "tesoreria", "aeat": "aeat", "workflow": "workflow", "bi": "bi",
}

# Módulos siempre accesibles (no se gatean nunca).
_SIEMPRE = {"saas", "notificaciones", "seguridad", "logout", "menu", "config"}


def nivel_acceso(id_empresa=None) -> str:
    """normal (activa/prueba/sin licencia), lectura (suspendida), bloqueado (cancelada/bloqueada)."""
    estado = _L.estado_operativo(id_empresa)
    if estado in ("sin_licencia", "activa", "prueba"):
        return "normal"
    if estado == "suspendida":
        return "lectura"
    return "bloqueado"          # cancelada | bloqueada


def exigir_modulo(modulo, id_empresa=None):
    """Backend: valida módulo + estado. Lanza LicenciaError si no procede (legacy → pasa)."""
    if nivel_acceso(id_empresa) == "bloqueado":
        raise _L.LicenciaError("Suscripción bloqueada o cancelada: renueve para continuar")
    _L.validar_operacion(modulo=modulo, id_empresa=id_empresa)
    return True


def acceso_modulo(v_id, id_empresa=None) -> tuple:
    """Gate del menú: (permitido, motivo). El portal SaaS siempre accesible para renovar."""
    if v_id in _SIEMPRE:
        return True, ""
    nivel = nivel_acceso(id_empresa)
    if nivel == "bloqueado":
        return False, "Suscripción bloqueada o cancelada. Renueve desde el portal SaaS."
    modulo = MODULO_POR_VID.get(v_id)
    if modulo and not _L.modulo_habilitado(modulo, id_empresa):
        lic = _L.licencia_activa(id_empresa)
        plan = lic["codigo_plan"] if lic else "—"
        return False, f"El módulo «{modulo}» no está incluido en tu plan ({plan}). Mejora tu plan."
    return True, ""
