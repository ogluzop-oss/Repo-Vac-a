"""
Experiencia de PRIMEROS PASOS (R1): estado del ASISTENTE de bienvenida y del MODO PYME SIMPLE.

Persistencia local per-install en ``config_onboarding.json`` (mismo patrón JSON que
``services/verticales.py``; sin BD). Este módulo NO tiene PyQt ni lógica de negocio: solo estado +
la regla de qué módulos son ESENCIALES para el modo simple. Lo consumen el asistente
(``gui/onboarding_wizard.py``), el menú (``gui/menu_principal.py``) y Configuración.
"""

import json
import logging
import os

logger = logging.getLogger("onboarding")

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_CONFIG = os.path.join(_RAIZ, "config_onboarding.json")

# v_id de los módulos ESENCIALES que se ven en MODO PYME SIMPLE (el resto se oculta del menú):
# facturación/contabilidad, clientes, cobros (tesorería+banco y gestión de caja), TPV, artículo,
# stock, compras/proveedores y configuración. Configuración y Salir siempre visibles.
ESENCIALES = {
    "tpv", "contabilidad", "clientes_crm", "tesoreria", "gestion_caja",
    "info", "stock", "compras", "configuracion", "logout",
}


def _leer() -> dict:
    """Lee el config de onboarding (tolerante: fichero inexistente/corrupto → {})."""
    try:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _guardar(data: dict) -> bool:
    try:
        with open(RUTA_CONFIG, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("onboarding _guardar: %s", e)
        return False


# ── Asistente de bienvenida ───────────────────────────────────────────────────
def completado() -> bool:
    """¿El asistente de bienvenida ya se completó u omitió alguna vez?"""
    return bool(_leer().get("completado"))


def marcar_completado(valor: bool = True) -> bool:
    """Marca (o desmarca) el asistente como completado/omitido. Idempotente."""
    d = _leer(); d["completado"] = bool(valor)
    return _guardar(d)


# ── Modo pyme simple ──────────────────────────────────────────────────────────
def modo_simple() -> bool:
    """¿Está activo el MODO PYME SIMPLE (menú reducido a lo esencial)?"""
    return bool(_leer().get("modo_simple"))


def fijar_modo_simple(activo: bool) -> bool:
    """Activa/desactiva el modo pyme simple (per-install)."""
    d = _leer(); d["modo_simple"] = bool(activo)
    return _guardar(d)


def esencial(v_id) -> bool:
    """True si el módulo (por su v_id de menú) debe verse en modo simple."""
    return str(v_id or "") in ESENCIALES


# ── Ayuda para decidir si conviene sugerir el asistente ───────────────────────
def datos_empresa_incompletos(id_empresa=None) -> bool:
    """True si a la empresa activa le faltan datos básicos (nombre real o CIF): señal de primera
    ejecución para sugerir el asistente. Best-effort: ante cualquier error → False (no molestar)."""
    try:
        from src.db.empresa import info_documento
        i = info_documento(id_empresa) or {}
        nombre = (i.get("nombre") or "").strip().upper()
        sin_nombre = (not nombre) or nombre == "SMART MANAGER"
        sin_cif = not (i.get("cif") or "").strip()
        return bool(sin_nombre or sin_cif)
    except Exception:
        return False
